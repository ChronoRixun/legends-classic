"""peek.py <pe> <va-hex> [...] : print the C string at each VA."""
import sys, pefile
pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
for a in sys.argv[2:]:
    va = int(a, 16)
    off = va - base
    end = img.find(b'\0', off)
    print(hex(va), repr(img[off:end][:200]))
