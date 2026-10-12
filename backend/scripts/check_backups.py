import gzip
import pathlib
import sys
from bson.json_util import loads

p = pathlib.Path('backups')
files = sorted(p.glob('*.json.gz'))
if not files:
    print('No backup files found in backups/')
    sys.exit(0)

for f in files:
    print('Checking', f.name)
    ok = True
    with gzip.open(f, 'rt', encoding='utf-8') as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                loads(line)
            except Exception as e:
                print('  invalid JSON on line', i+1, '-', e)
                ok = False
                break
            if i >= 9:
                break
    print('  OK' if ok else '  FAIL')
