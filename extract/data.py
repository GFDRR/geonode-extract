import os
import json
import zipfile
import requests
import urlparse

def get_data(url, dest_dir='data'):
    output_dir = os.path.abspath(dest_dir)
    print 'Getting data from "%s" into "%s"' % (url, output_dir)

    # Create output directory if it does not exist
    if not os.path.isdir(output_dir):
        os.makedirs(dest_dir)

    # Get the list of layers from GeoNode's search api JSON endpoint
    search_api_endpoint = urlparse.urljoin(url, '/data/search/api')
    print 'Retriving list of layers from "%s"' % search_api_endpoint
    r = requests.get(search_api_endpoint)
    data = json.loads(r.text)
    print 'Found %s layers, starting extraction' % data['total']

    layers = data['rows']
    supported_formats = ['zip', 'geotiff']
    for layer in layers[:1]:
        # download_links is originally a list of lists, each item looks like:
        # ['zip', 'Zipped Shapefile', 'http://...//'], this operation
        # transforms it into a simple dict, with items like:
        # {'zip': 'http://.../'}
        download_links = dict([ (a, c) for a, b, c in layer['download_links']])

        # Find out the appropiate download format for this layer
        for f in supported_formats:
            if f in download_links:
                download_format = f
                break
        else:
            msg = 'Only "%s" are supported for the extract, available formats for "%s" are: "%s"' % (
                                             ', '.join(supported_formats),
                                             layer['title'],
                                             ', '.join(download_links.keys()))
            raise Exception(msg)

        download_link = download_links[download_format]
        print 'Download link for this layer is "%s"' % download_link

        try:
            # Download the file
            r = requests.get(download_link)
            # FIXME(Ariel): This may be dangerous if file is too large.
            content = r.content

            # Figure out the filename based on the 'content-disposition' header.
            filename = r.headers['content-disposition'].split('filename=')[1]
            layer_filename = os.path.join(dest_dir, filename)
            with open(layer_filename, 'wb') as layer_file:
                layer_file.write(content)
                print 'Saved "%s" as "%s"' % (layer['title'], layer_filename)

                print 'Is "%s" a zipfile? %s' % (layer_filename, zipfile.is_zipfile(layer_filename))
        except Exception, e:
            print 'There was a problem downloading "%s": %s' % (layer['title'], str(e))
            raise e
