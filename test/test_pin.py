import sys
sys.path.append('../src')
sys.path.append('../f469-disco/tests')
from pin import Secret, Factory_settings
from platform import storage_root
from unittest import TestCase
import os

class PinTest(TestCase):

    def test_factory_settings(self):
        """"
         We create the following structure of files and folders:

         userdata
             - f0.txt
             - test1
                 - f1.txt
             - test2
                 - f2.txt
        """
        try:
            os.mkdir(storage_root)
        except:
            pass

        test_folder1 = "%s/%s" % (storage_root, "test1")
        test_folder2 = "%s/%s" % (storage_root, "test2")
        os.mkdir(test_folder1)
        os.mkdir(test_folder2)

        f0 = "%s/%s" % (storage_root, "f0.txt")
        f1 = "%s/%s" % (test_folder1, "f1.txt")
        f2 = "%s/%s" % (test_folder2, "f2.txt")

        content = "test123"

        with open(f0, "w") as f:
            f.write(content)

        with open(f1, "w") as f:
            f.write(content)

        with open(f2, "w") as f:
            f.write(content)

        # blacklist a file
        Factory_settings.blacklist.append("f1.txt")
        # blacklist a folder
        Factory_settings.blacklist.append("test2")
        Factory_settings.restore()

        # we should not be able to read f0.txt
        try:
            with open(f0, "r") as f:
                assert False
        except:
            assert True

        # we should be able to read files f1 and f2
        for _file in [f1, f2]:
            try:
                with open(_file, "r") as f:
                    assert f.read() == content
            except:
                assert False

        # Remove the blacklisted file and folder
        Factory_settings.blacklist.pop()
        Factory_settings.blacklist.pop()
        Factory_settings.restore()

        # we should not be able to read any files
        for _file in [f0, f1, f2]:
            try:
                with open(_file, "r") as f:
                    assert False
            except:
                assert True
