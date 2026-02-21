import re, json, sys
from pathlib import Path
logp = Path(r"C:\Users\hn2_f\.nanobot\workspace\skills\moltbook\events.log")
outdir = Path(r"C:\Users\hn2_f\.nanobot\workspace\skills\moltbook\data")
outdir.mkdir(parents=True, exist_ok=True)
log = logp.read_text(encoding='utf8', errors='replace')
lines = log.splitlines()
# parse
upvoted = []
upvote_submolt_counts = {}
comment_attempts = []
comment_success = []
comment_failures = []
verifications = []
lurk_runs = []
wakeup_runs = []
for L in lines:
    # Upvoted post ... via
    m = re.search(r"Upvoted post ([0-9a-fA-F\-]+) via", L)
    if m:
        upvoted.append(m.group(1))
    m2 = re.search(r"Upvoted (\d+) posts in submolt (\w+)", L)
    if m2:
        cnt = int(m2.group(1)); sub = m2.group(2)
        upvote_submolt_counts[sub] = upvote_submolt_counts.get(sub,0)+cnt
    m3 = re.search(r"Will POST comment to /posts/([0-9a-fA-F\-]+)/comments with content: (.*)$", L)
    if m3:
        comment_attempts.append({'post_id':m3.group(1),'content':m3.group(2)})
    if 'POST /posts/' in L and 'failed: no response' in L:
        m4 = re.search(r"POST /posts/([0-9a-fA-F\-]+)/comments failed: no response", L)
        if m4:
            comment_failures.append(m4.group(1))
    if re.search(r"Posted comment to ([0-9a-fA-F\-]+): response keys", L):
        m5 = re.search(r"Posted comment to ([0-9a-fA-F\-]+): response keys: (.*)$", L)
        if m5:
            comment_success.append({'post_id':m5.group(1),'resp':m5.group(2)})
    # verifications
    m6 = re.search(r"Found verification challenge for (?:comment on post |post |comment )?([0-9a-fA-F\-]+); saved to pending_verifications.json", L)
    if m6:
        verifications.append({'post_id':m6.group(1),'line':L})
    m7 = re.search(r"Moltbook pending verification detected: code=([^,]+), post/comment=([^,]+), challenge=(.*)$", L)
    if m7:
        verifications.append({'code':m7.group(1),'post_id':m7.group(2),'challenge':m7.group(3)})
    # lurk runs
    if 'Starting lurk in' in L:
        lurk_runs.append(L)
    if 'Batch actions completed' in L:
        lurk_runs.append('Batch actions completed')
    # wake up dead internet marker
    if 'Running one-shot monitor_replies' in L or 'Wake Up Dead Internet' in L:
        wakeup_runs.append(L)

# Summaries
lurker_summary = []
lurker_summary.append(f"Lurker runs detected: {len([x for x in lines if 'Starting lurk in' in x])}")
for sub,c in upvote_submolt_counts.items():
    lurker_summary.append(f"Upvoted {c} posts in submolt {sub}")
lurker_summary.append(f"Total individual upvote calls recorded: {len(upvoted)}")
lurker_summary.append(f"Comment attempts: {len(comment_attempts)}")
lurker_summary.append(f"Comment successes (posted with response): {len(comment_success)}")
lurker_summary.append(f"Comment failures (no response): {len(comment_failures)}")
lurker_summary.append(f"Verification challenges saved: {len(verifications)}")

wakeup_summary = []
wakeup_summary.append(f"One-shot monitor_replies runs detected: {len(wakeup_runs)}")
wakeup_summary.append("Note: monitor_replies often falls back to scanning and may report API probe status in events.log.")

# write detailed lists
lurker_report = outdir / 'lurker_report.txt'
wakeup_report = outdir / 'wakeup_report.txt'
with open(lurker_report,'w',encoding='utf8') as f:
    f.write('LURKER REPORT\n')
    f.write('\n'.join(lurker_summary)+"\n\n")
    f.write('-- Upvoted post IDs (first 200):\n')
    for uid in upvoted[:200]:
        f.write(uid+'\n')
    f.write('\n-- Comment attempts (post_id -> excerpt):\n')
    for c in comment_attempts:
        f.write(f"{c['post_id']} -> {c['content'][:140]}\n")
    f.write('\n-- Comment successes:\n')
    for c in comment_success:
        f.write(f"{c['post_id']} -> {c['resp']}\n")
    f.write('\n-- Comment failures (no response):\n')
    for cf in comment_failures:
        f.write(cf+'\n')
    f.write('\n-- Verifications: \n')
    for v in verifications:
        f.write(json.dumps(v,ensure_ascii=False)+'\n')

with open(wakeup_report,'w',encoding='utf8') as f:
    f.write('WAKEUP (one-shot monitor) REPORT\n')
    f.write('\n'.join(wakeup_summary)+"\n\n")
    f.write('Recent monitor_replies status excerpts:\n')
    for L in lines[-1000:]:
        if any(k in L for k in ('monitor_replies','/agents/me','Using discovered read endpoint','probe returned','Running one-shot monitor_replies','Sanitized pending_verifications.json')):
            f.write(L+'\n')

print('Wrote reports:')
print(str(lurker_report))
print(str(wakeup_report))
