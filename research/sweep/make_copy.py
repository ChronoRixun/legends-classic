"""Make a writable copy of the real XML2 install for the conversion sweep.
Movies (*.sfd) and Sounds are skipped: convert_zone.py never reads or writes them."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, shutil, sys, time

SRC = _XML2
DST = _REPO + r'\research\sweep\xml2_copy'

t = time.time()
if os.path.exists(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST, ignore=lambda d, names: [n for n in names if n.lower().endswith('.sfd')
                                                   or (os.path.samefile(d, SRC) and n == 'Sounds')])
print('copied in %.1fs' % (time.time() - t))
