import sys
import os

def write_to(fout, path, top_level=True):
    files = os.listdir(path)
    name = None
    for file in files:
        fname = os.path.join(path, file)
        if os.path.isdir(fname):
            write_to(f, fname, top_level=False)
            continue
        # files
        fout.write("\n########## %s ##########\n" % fname)
        with open(fname,"r") as fin:
            lines = fin.readlines()
        for line in lines:
            if top_level and file == "__init__.py":
                if " as App" in line and "import " in line:
                    name = line.split(" as App")[0].strip().split(" ")[-1]
            ll = line.strip().replace("  ", "")
            # ugly but works in most cases
            if ll.startswith("from .") and "import" in ll:
                continue
            fout.write(line)
    if name is not None:
        fout.write("\nApp = %s\n" % name)

def main():
    if len(sys.argv) != 2:
        print("usage: %s /path/to/dir/" % sys.argv[0])
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.isdir(path):
        print("%s is not a directory" % path)
        sys.exit(1)
    with open(path.rstrip("/")+".py", "w") as f:
        write_to(f, path)

if __name__ == '__main__':
    main()