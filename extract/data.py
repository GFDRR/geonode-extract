import os

def get_data(url, dest_dir='data'):
    output_dir = os.path.abspath(dest_dir)
    print 'Getting data from "%s" into "%s"' % (url, output_dir)
