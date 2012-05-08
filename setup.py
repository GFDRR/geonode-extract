#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import subprocess

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

# If it is possible, build the manpage
# This seemed to be the cause of problems in pypi
cmdclass = {}
try:
    from extract.build_manpage import build_manpage
except ImportError,e:
    print "Warning, Could not build manpage."
else:
    cmdclass['build_manpage'] = build_manpage


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

MAJOR = 0
MINOR = 3
MICRO = 4
ISRELEASED = True
VERSION = '%d.%d.%d' % (MAJOR, MINOR, MICRO)

# Return the git revision as a string
def git_version():
    def _minimal_ext_cmd(cmd):
        # construct minimal environment
        env = {}
        for k in ['SYSTEMROOT', 'PATH']:
            v = os.environ.get(k)
            if v is not None:
                env[k] = v
        # LANGUAGE is used on win32
        env['LANGUAGE'] = 'C'
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        out = subprocess.Popen(cmd, stdout = subprocess.PIPE, env=env).communicate()[0]
        return out

    try:
        out = _minimal_ext_cmd(['git', 'rev-parse', 'HEAD'])
        GIT_REVISION = out.strip().decode('ascii')
    except OSError:
        GIT_REVISION = "Unknown"

    return GIT_REVISION

def write_version_py(filename='extract/version.py'):
    cnt = """# THIS FILE IS GENERATED FROM setup.py in geonode-extract
short_version = '%(version)s'
version = '%(version)s'
full_version = '%(full_version)s'
git_revision = '%(git_revision)s'
release = %(isrelease)s

if not release:
    version = full_version
"""
    # Adding the git rev number needs to be done inside write_version_py(),
    # otherwise the import of extract.version messes up the build under Python 3.
    FULLVERSION = VERSION
    if os.path.exists('.git'):
        GIT_REVISION = git_version()
    elif os.path.exists('extract/version.py'):
        # must be a source distribution, use existing version file
        GIT_REVISION = "Unknown"

    if not ISRELEASED:
        FULLVERSION += '.dev-' + GIT_REVISION[:7]

    a = open(filename, 'w')
    try:
        a.write(cnt % {'version': VERSION,
                       'full_version' : FULLVERSION,
                       'git_revision' : GIT_REVISION,
                       'isrelease': str(ISRELEASED)})
    finally:
        a.close()

    return FULLVERSION


# Creates extract/version.py and returns the full version
full_version = write_version_py()

setup(name          = 'geonode-extract',
      version       = full_version,
      description   = 'Extract data from a geonode and put it in a folder',
      license       = 'BSD',
      keywords      = 'gis vector feature raster data',
      author        = 'Ariel Núñez',
      author_email  = 'ingenieroariel@gmail.com',
      maintainer        = 'Ariel Núñez',
      maintainer_email  = 'ingenieroariel@gmail.com',
      url   = 'http://github.com/GFDRR/geonode-extract',
      long_description = read('README'),
      packages = ['extract',],
      scripts = ['scripts/geonode-extract',],
#      data_files = [('/usr/share/man/man1', ['geonode-extract.1']),],
      install_requires = ['requests',],
      cmdclass=cmdclass,
      classifiers   = [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering :: GIS',
        ],
)
