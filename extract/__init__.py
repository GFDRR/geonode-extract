# Make the version available if there is a version.py file
try:
    from safe.version import git_revision as __git_revision__
except ImportError:
    __version__ = "unknwon"
    __git_revision__ = None

