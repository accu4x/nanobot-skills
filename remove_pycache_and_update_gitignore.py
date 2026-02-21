import os, shutil
root = r"C:\Users\hn2_f\source\repos\nanobot-skills"
removed = []
for dirpath, dirs, files in os.walk(root):
    if '__pycache__' in dirs:
        p = os.path.join(dirpath, '__pycache__')
        try:
            shutil.rmtree(p)
            removed.append(p)
        except Exception as e:
            print('ERROR removing', p, e)
# Update .gitignore entries
gitignore = os.path.join(root, '.gitignore')
entries = [
    '**/data/',
    '**/data/faiss_index/',
    '**/*.env',
    'MEMORY.md',
    'pending_verifications.json',
    '__pycache__/',
    '*.pyc'
]
existing = set()
try:
    if os.path.exists(gitignore):
        with open(gitignore, 'r', encoding='utf-8') as f:
            for line in f:
                existing.add(line.strip())
    with open(gitignore, 'a', encoding='utf-8') as f:
        f.write('\n# added by replace-userpath\n')
        for e in entries:
            if e not in existing:
                f.write(e + '\n')
    print('gitignore updated')
except Exception as e:
    print('ERROR updating gitignore', e)
for p in removed:
    print('removed', p)
print('done')
