from __future__ import with_statement

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
import traceback as tb
from xml.dom import minidom

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
parser.add_option("-q", "--query", dest="query",
                          help="Search terms")
parser.add_option("-v", dest="verbose", default=1, action="count",
                      help="increment output verbosity; may be specified multiple times")

SUPPORTED_FORMATS = ['zip', 'tiff']


def get_parser():
    return parser


def download_layer(layer_name, url,  dest_dir='data', username=None, password=None):
    
    #Dictionnary to store the path of the file downloaded, later on could be stored in a layer object
    layer_paths = {'data': None, 'metadata': None, 'style': None}

    #Necessary because there is currently a bug in search api where no results are returned if the name contains ":"
    #To remove when fixed in Geonode
    if ':' in layer_name:
        layer_name_clean = layer_name.split(':')[1]
    else:
        layer_name_clean = layer_name
    query_name = layer_name_clean

    layers = get_layer_list(url, query=query_name)

    if len(layers) == 0:
        msg = 'There is no layer with this name: "%s"; no layer downloaded' % (layer_name_clean)
        log.error(msg)
        raise RuntimeError(msg)
    elif len(layers) > 1:
        msg = 'Several layers with the same name "%s"; no layer downloaded' % (layer_name_clean)
        log.error(msg)
        raise RuntimeError(msg)
    else:
        layer=layers[layer_name] 

    links = layer['links']

    # Find out the appropiate download format for this layer
    for f in SUPPORTED_FORMATS:
        if f in links:
            download_format = f
            break
    else:
        msg = 'Only "%s" are supported for the extract, available formats for "%s" are: "%s"' % (
                                         ', '.join(SUPPORTED_FORMATS),
                                         layer['name'],
                                         ', '.join(links.keys()))
        log.error(msg)
        raise RuntimeError(msg)

    download_link = links[download_format]['url']
    log.debug('Download link for this layer is "%s"' % download_link)

    try:
        # Download the file
        log.debug('Starting data download for "%s"' % layer['name'])
        r = requests.get(download_link)
        log.debug('Finished downloading data for "%s"' % layer['name'])
    except Exception, e:
        log.exception('There was a problem downloading "%s".' % layer['name'])
        raise e
    else:
        # FIXME(Ariel): This may be dangerous if file is too large.
        content = r.content

        if 'content-disposition' not in r.headers:
            msg = ('Layer "%s" did not have a valid download link "%s"' %
                    (layer['name'], download_link))
            log.error(msg)
            raise RuntimeError(msg)
        
        filename = layer['name'] + links[download_format]['extension']

        # Strip out the 'geonode:' if it exists
        if ':' in filename:
            filename = layer['name'].split(':')[1]
        
        output_dir = os.path.abspath(dest_dir)
        log.info('Getting data from "%s" into "%s"' % (url, output_dir))

        # Create output directory if it does not exist
        if not os.path.isdir(output_dir):
            os.makedirs(dest_dir)
        
        layer_filename = os.path.join(dest_dir, filename)
        base_filename, extension = os.path.splitext(layer_filename)
        with open(layer_filename, 'wb') as layer_file:
            layer_file.write(content)
            if extension == '.tiff':
                layer_paths['data']=os.path.abspath(layer_filename)
            log.debug('Saved data from "%s" as "%s"' % (layer['name'], layer_filename))

    # If this file a zipfile, unpack all files with the same base_filename
    # and remove the downloaded zip
    if zipfile.is_zipfile(layer_filename):
        log.debug('Layer "%s" is zipped, unpacking now' % layer_filename)
        # Create a ZipFile object
        z = zipfile.ZipFile(layer_filename)
        for f in z.namelist():
            log.debug('Found "%s" in "%s"' % (f, layer_filename))
            _, extension = os.path.splitext(f)
            filename = base_filename + extension
            log.debug('Saving "%s" to "%s"' % (f, filename))
            z.extract(f, dest_dir)
            os.rename(os.path.join(dest_dir, f), filename)
            #FIXME(Viv): Needs to be more flexible to take into account different file formats
            if extension == '.shp':
                layer_paths['data']=os.path.abspath(filename)
        log.debug('Removing "%s" because it is not needed anymore' % layer_filename)
        os.remove(layer_filename)

    metadata_link = links['xml']['url']

    metadata_filename = base_filename + '.xml'
    try:
        # Download the file
        r = requests.get(metadata_link)
        content = r.content
    except Exception, e:
        log.error('There was a problem downloading "%s": %s' % (layer['name'], str(e)), e)
        raise e
    else:
        domcontent = minidom.parseString(content)
        gmd_tag = 'gmd:MD_Metadata'
        metadata = domcontent.getElementsByTagName(gmd_tag)

        msg = 'Expected one and only one <%s>' % gmd_tag
        assert len(metadata) == 1, msg

        md_node = metadata[0]

        domcontent.childNodes = [md_node]
        raw_xml = domcontent.toprettyxml().encode('utf-8')

        with open(metadata_filename, 'wb') as metadata_file:
            metadata_file.write(raw_xml)
            layer_paths['metadata']=os.path.abspath(metadata_filename)
            log.debug('Saved metadata from "%s" as "%s"' % (layer['name'], metadata_filename))

    style_link = links['sld']['url']

    style_filename = base_filename + '.sld'

    try:
        # Download the file
        r = requests.get(style_link)
        content = r.content
    except Exception, e:
        log.error('There was a problem downloading "%s": %s' % (layer['name'], str(e)), e)
        raise e
    else:
        style_data = r.content
        xml_style_data = minidom.parseString(style_data)
        pretty_style_data = xml_style_data.toprettyxml().encode('utf-8')

        with open(style_filename, 'wb') as style_file:
            style_file.write(pretty_style_data)
            layer_paths['style']=os.path.abspath(style_filename)
            log.debug('Saved style from "%s" as "%s"' % (layer['name'], style_filename))

    return layer_paths
            
            
def get_layer_list(url, query=None, endpoint='/search/api'):
    """ Get the list of layers from GeoNode's search api JSON endpoint
    
    Return a dictionnary of layers with the layer name as the key
    """   
    
    # Get one page of the layer list when since the search API may return paginated results, 
    def get_layer_list_page(url,query,endpoint):
        search_api_endpoint = urlparse.urljoin(url, endpoint)
        log.debug('Retrieving list of layers from "%s"' % search_api_endpoint)
        payload = {}
        if query is not None:
            payload['q'] = query
        try:
            r = requests.get(search_api_endpoint, params=payload)
        except requests.exceptions.ConnectionError, e:
            log.exception('Could not connect to %s, are you sure you are connected to the internet?' % search_api_endpoint)
            raise e
        data = json.loads(r.text)
    
        if data['success']==False:
            msg = 'Geonode search returned the following errors "%s"' % (','.join(data['errors']))
            log.error(msg)
            raise RuntimeError(msg)
        else:
            return data   
                     
    # Get the first page of data
    data = get_layer_list_page(url, query, endpoint)
    total = data['total']
    log.info('Found %s layers' % total)
    all_layers = data['results']
    
    # Repeat the process if there are several pages
    if 'next' in data:
        next_list = data['next']
    else:
        next_list = None

    while(next_list is not None):
        new_data = get_layer_list(url, endpoint=next_list)
        new_layers = new_data['rows']
        next_list = new_data['next']

        if len(new_layers)==0:
            break

        all_layers.extend(new_layers)
    
    #Transform the list of layers in a dictionnary of layers for ease of use later on
    #In Python 3 use a dict comprehension instead: layers = {layer['name']:layer for layer in all_layers}
    layers = {}
    for layer in all_layers:
        name = layer['name'] 
        layers[name] = layer
    
    return layers
     

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
    query = options.query
    output_dir = os.path.abspath(dest_dir)
    log.info('Getting data from "%s" into "%s"' % (url, output_dir))

    # Create output directory if it does not exist
    if not os.path.isdir(output_dir):
        os.makedirs(dest_dir)


    layers = get_layer_list(url, query)
    
    if limit is not None:
        if limit < len(layers):
            layers =layers[:limit]

    number = len(layers)
    log.info('Processing %s layers' % number)
    output = []
    i=0
    for layer_name,layer in layers.iteritems():
        if ':' in layer['name']:
            name = layer['name'].split(':')[1]
        else:
            name = layer['name']

        if os.path.exists(os.path.join(dest_dir, name + '.sld')):
            status = 'skipped'
        else:
            try:
                download_layer(layer['name'], url, dest_dir, username, password)
            except Exception, e:
                log.exception('Could not download layer "%s".' % layer['name'])
                exception_type, error, traceback = sys.exc_info()
                status = 'failed'
                if not ignore_errors:
                    msg = "Stopping process because --ignore-errors was not set and an error was found."
                    log.error(msg)
                    sys.exit(-1)
            else:
               status = 'downloaded'

        info = {'name': layer['name'], 'title': layer['title'], 'status': status}
        msg = "[%s] Layer %s (%d/%d)" % (info['status'], info['name'], i+1, number)
        log.info(msg)
        i += 1
        
        if status == 'failed':
           info['traceback'] = traceback
           info['exception_type'] = exception_type
           info['error'] = error

        output.append(info)

    downloaded = [dict_['name'] for dict_ in output if dict_['status']=='downloaded']
    failed = [dict_['name'] for dict_ in output if dict_['status']=='failed']
    skipped = [dict_['name'] for dict_ in output if dict_['status']=='skipped']
    finish = datetime.datetime.now()
    td = finish - start
    duration = td.microseconds / 1000000 + td.seconds + td.days * 24 * 3600
    duration_rounded = round(duration, 2)

    log.debug("\nDetailed report of failures:")
    for dict_ in output:
        if dict_['status'] == 'failed':
            log.debug(dict_['name'])
            tb.print_exception(dict_['exception_type'],
                                      dict_['error'],
                                      dict_['traceback'])

    log.info("Finished processing %d layers in %s seconds." % (
                              len(output), duration_rounded))
    log.info("%d Downloaded layers" % len(downloaded))
    log.info("%d Failed layers" % len(failed))
    log.info("%d Skipped layers" % len(skipped))
    if len(output) > 0:
        log.info("%f seconds per layer" % (duration * 1.0 / len(output)))
