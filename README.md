# moodle2qti
Convert Moodle questionbank XML file to QTI folder structure. Zip it and test import into other LMS or Testtool.
Usage: first install python and after that, the lxml package with "pip install lxml"

Export a questionbank as Moodle XML and copy the file as "moodleq.xml" in the same folder as the python file.

Run python moodle2QTI.py --dumpfiles  to only export the pictures and media files from the xml (base64-encoded)
Run python moodle2QTI.py -h to see other options.


