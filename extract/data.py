import os
import sys
import json
import zipfile
import requests
import urlparse
import logging
import datetime
from extract import __version__
from optparse import OptionParser

log = logging.getLogger("geonode-extract")

# Usual logging boilerplate, unnecessary in Python >= 3.1.
try:
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record): pass
log.addHandler(NullHandler())

parser = OptionParser(usage="%prog <geonode_url> [options]",
                      version="%prog " + __version__)

parser.add_option("-d", "--dest-dir", dest="dest_dir",
                          help="write data to dir", default='data', metavar="PATH")
parser.add_option("-u", "--username", dest="username",
                          help="GeoNode username")
parser.add_option("-p", "--password", dest="password",
                          help="GeoNode password")
parser.add_option("-i", "--ignore-errors", action="store_true", dest='ignore_errors', default=False,
                          help="Stop after any errors are encountered")
parser.add_option("-l", "--limit", dest="limit", type="int",
                          help="Limit the number of layers to be extracted")
parser.add_option("-v", dest="verbose", default=1, action="count",
                      help="increment output verbosity; may be specified multiple times")

SUPPORTED_FORMATS = ['zip', 'geotiff']


def get_parser():
    return parser

def get_style(layer, username=None, password=None):
    """Downloads the associated SLD file for a given GeoNode layer

       The current implementation goes to the layer's detail page and follows the
       link to the GeoServer's REST API endpoint. It needs the username and password,
       because by default GeoServer restricts read access to those.

       It returns the raw content of the SLD file in text format.
    """
    return "nothing"

def download_layer(layer, dest_dir, username=None, password=None):
    # download_links is originally a list of lists, each item looks like:
    # ['zip', 'Zipped Shapefile', 'http://...//'], this operation
    # transforms it into a simple dict, with items like:
    # {'zip': 'http://.../'}
    download_links = dict([ (a, c) for a, b, c in layer['download_links']])

    # Find out the appropiate download format for this layer
    for f in SUPPORTED_FORMATS:
        if f in download_links:
            download_format = f
            break
    else:
        msg = 'Only "%s" are supported for the extract, available formats for "%s" are: "%s"' % (
                                         ', '.join(SUPPORTED_FORMATS),
                                         layer['title'],
                                         ', '.join(download_links.keys()))
        log.error(msg)
        raise Exception(msg)

    download_link = download_links[download_format]
    log.debug('Download link for this layer is "%s"' % download_link)

    try:
        # Download the file
        r = requests.get(download_link)
    except Exception, e:
        log.error('There was a problem downloading "%s".' % layer['title'],e)
        raise e
    else:
        # FIXME(Ariel): This may be dangerous if file is too large.
        content = r.content
            
        if 'content-disposition' not in r.headers:
            msg = ('Layer "%s" did not have a valid download link "%s"' % 
                    (layer['title'], download_link))
            log.error(msg)
            raise Exception(msg)
        # Figure out the filename based on the 'content-disposition' header.
        filename = r.headers['content-disposition'].split('filename=')[1]
        layer_filename = os.path.join(dest_dir, filename)
        with open(layer_filename, 'wb') as layer_file:
            layer_file.write(content)
            log.debug('Saved data from "%s" as "%s"' % (layer['title'], layer_filename))

    # metadata_links is originally a list of lists, each item looks like:
    # ['text/xml', 'TC211', 'http://...//'], this operation
    # transforms it into a simple dict, with items like:
    # {'TC211': 'http://.../'}
    metadata_links = dict([ (b, c) for a, b, c in layer['metadata_links']])
    metadata_link = metadata_links['TC211']

    base_filename, extension = os.path.splitext(layer_filename)
    metadata_filename = base_filename + '.xml'
    try:
        # Download the file
        r = requests.get(metadata_link)
        content = r.content
    except Exception, e:
        log.error('There was a problem downloading "%s": %s' % (layer['title'], str(e)), e)
        raise e
    else:
        with open(metadata_filename, 'wb') as metadata_file:
            metadata_file.write(content)
            log.debug('Saved metadata from "%s" as "%s"' % (layer['title'], metadata_filename))

    # Download the associated style
    style_data = get_style(layer, username, password)
    style_filename = base_filename + '.sld'
    with open(style_filename, 'wb') as style_file:
        style_file.write(style_data)
        log.debug('Saved style from "%s" as "%s"' % (layer['title'], style_filename))

def get_data(argv=None):
    # Get the arguments passed or get them from sys
    the_argv = argv or sys.argv[:]
    options, original_args = parser.parse_args(the_argv)

    # For each -v passed on the commandline, a lower log.level will be enabled.
    # log.ERROR by default, log.INFO with -vv, etc.
    log.addHandler(logging.StreamHandler())
    log.level = max(logging.ERROR - (options.verbose * 10), 1)

    start = datetime.datetime.now()

    args = original_args[1:]
    if len(args) != 1:
        parser.error('Please supply a <geonode_url>, for example: http://demo.geonode.org')

    url = args[0]
    dest_dir = options.dest_dir
    ignore_errors = options.ignore_errors

    #FIXME(Ariel): Add validation. Both arguments should be supplied if one of them is specified.
    username = options.username
    password = options.password

    limit = options.limit

    output_dir = os.path.abspath(dest_dir)
    log.info('Getting data from "%s" into "%s"' % (url, output_dir))

    # Create output directory if it does not exist
    if not os.path.isdir(output_dir):
        os.makedirs(dest_dir)

    # Get the list of layers from GeoNode's search api JSON endpoint
    search_api_endpoint = urlparse.urljoin(url, '/data/search/api')
    log.debug('Retrieving list of layers from "%s"' % search_api_endpoint)
    try:
        r = requests.get(search_api_endpoint)
    except requests.exceptions.ConnectionError, e:
        log.error('Could not connect to %s, are you sure you are connected to the internet?' % search_api_endpoint)
        raise e
    data = json.loads(r.text)
    log.info('Found %s layers, starting extraction' % data['total'])

    all_layers = data['rows']


    layers = all_layers

    if limit is not None:
        if limit < len(all_layers):
            layers = all_layers[:limit]

    number = len(layers)
    log.info('Processing %s layers' % number)
    output = []
    for i, layer in enumerate(layers):
        try:
            download_layer(layer, dest_dir, username, password)
        except Exception, e:
            log.error('Could not download layer "%s".' % layer['title'], e) 
            exception_type, error, traceback = sys.exc_info()
            status = 'failed'
        else:
            status = 'downloaded'

        info = {'name': layer['name'], 'title': layer['title'], 'status': status}
        msg = "[%s] Layer %s (%d/%d)" % (info['status'], info['name'], i, number)
        log.info(msg)

        if status == 'failed':
           info['traceback'] = traceback
           info['exception_type'] = exception_type
           info['error'] = error
           if not ignore_errors:
               msg = "Stopping process because --ignore-errors was not set and an error was found."
               log.debug(msg)
               raise e

        output.append(info)

    downloaded = [dict_['name'] for dict_ in output if dict_['status']=='downloaded']
    failed = [dict_['name'] for dict_ in output if dict_['status']=='failed']
    finish = datetime.datetime.now()
    td = finish - start
    duration = td.microseconds / 1000000 + td.seconds + td.days * 24 * 3600
    duration_rounded = round(duration, 2)

    log.debug("\nDetailed report of failures:")
    for dict_ in output:
        if dict_['status'] == 'failed':
            log.debug("\n\n", dict_['name'], "\n================")
            traceback.print_exception(dict_['exception_type'],
                                      dict_['error'],
                                      dict_['traceback'])

    log.info("Finished processing %d layers in %s seconds." % (
                              len(output), duration_rounded))
    log.info("%d Downloaded layers" % len(downloaded))
    log.info("%d Failed layers" % len(failed))
    if len(output) > 0:
        log.info("%f seconds per layer" % (duration * 1.0 / len(output)))
