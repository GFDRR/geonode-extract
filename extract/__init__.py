# Make the version available if there is a version.py file
try:
    from extract.version import version as __version__
    from extract.version import git_revision as __git_revision__
except ImportError:
    __version__ = "unknwon"
    __git_revision__ = None


from extract.data import get_data
