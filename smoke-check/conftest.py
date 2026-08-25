import glob, os, sys
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
for _whl in sorted(glob.glob(os.path.join(_vendor, "*.whl"))):
    if _whl not in sys.path:
        sys.path.insert(0, _whl)
