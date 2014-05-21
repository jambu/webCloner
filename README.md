webCloner
=========

This repo contains script to clone a website locally

TODO
====

Stream download static assets. If there are big bulky images in the website it can consume a lot of RAM.

Update pages locally using mtime and http headers based comparison.

Filter download preferences by filetype. This is a bit costly as we should request http headers for every page before verifying the filetype.


Dependencies
============

https://pypi.python.org/pypi/html5lib

https://pypi.python.org/pypi/requests/

https://pypi.python.org/pypi/beautifulsoup4/4.3.2

https://pypi.python.org/pypi/tinycss


Run
===

python clone.py -h for Instructions
