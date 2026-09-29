import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import pefile, sys
pe = pefile.PE(_XML2 + '/XMen2.exe')
want = {int(a, 16) for a in sys.argv[1:]}
for e in pe.DIRECTORY_ENTRY_IMPORT:
    for i in e.imports:
        if i.address in want or not want:
            print(hex(i.address), e.dll.decode(), i.name.decode() if i.name else i.ordinal)
