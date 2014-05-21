import os, requests
import argparse
import html5lib
from bs4 import BeautifulSoup
import errno
import requests
from urlparse import urlparse, urljoin
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)

class Cloner(object):
  def __init__(self, *args, **kwargs):
    if not kwargs['directory']:
      self.root_dir = os.getcwd()
    elif kwargs['directory'].startswith('/'):
      self.root_dir = os.path.join(kwargs['directory'])
    else:
      self.root_dir = os.path.abspath(os.path.join(os.getcwd(), kwargs['directory']))
    self.websites = kwargs['websites']
    self.external_url = kwargs['external_url']
    self.urls_queue = []

  def go(self):
    
    for website in self.websites:
      if website.find('http') == -1: #Protocol not added to user input.
        website = '//' + website
      self.clone_website(website)

  def clone_website(self, website):
    
    root_host, root_path = self._get_host_and_path(website)
    root_url = root_host + root_path
    self.urls_queue.append(root_url)

    while self.urls_queue:
      current_url = self.urls_queue.pop(0)
      no_follow = False
      if current_url.find(root_host) == -1:#External URL
        no_follow = True
      self._process_page(current_url, no_follow=no_follow)
    self.urls_queue = []

    
  def _process_page(self, page_url, no_follow=False):

    result = self._get_page(page_url)
    if not result: # not a successful http request
      return #cant do much but ignore the page.

    markup = result.text
    content_type = result.headers['content-type']

    def process_link(attr, full_url_needed=False):
      
      absolute_url = urljoin(page_url, attr)

      #This is used for the case where links in the external page cannot be processed, 
      #however the link has to be changed to absolute url
      if full_url_needed:
        return absolute_url

      host, path = self._get_host_and_path(absolute_url)
      if not host:
        return None
      is_external_url = page_url.find(host) == -1
      if is_external_url and not self.external_url: #External URL
        return None

      filepath, filename = self._get_local_location(host, path)
      if not os.path.exists(os.path.join(filepath, filename)): # Already processed URL
        self.urls_queue.append(host+path)
        
      
      #This step replaces the url in the page with the standardized url. 
      #Usually static assets are served from a different server to prevent cookie transport for static assets.
      #Since we are storing everything locally, we need to rewrite all the urls and create directory structure
      #for storing external domain urls as well.
      if is_external_url:
         return os.path.join(filepath, filename)
      else:
         return path

    if content_type.find('text/html') == 0: #Process HTML file for more links

      #html5lib is a very lenient parser which mimicks the parsing of the browser.
      htmltree = BeautifulSoup(markup, "html5lib")
      for anchor in htmltree.select('a[href]'):
        adjusted_path = process_link(anchor['href'], full_url_needed=no_follow)
        if adjusted_path:
          anchor['href'] = adjusted_path
      for link in htmltree.select('link[href]'):
        adjusted_path = process_link(link['href'])
        if adjusted_path:
          link['src'] = adjusted_path 
      for script in htmltree.select('script[src]'):
        adjusted_path = process_link(script['src'])
        if adjusted_path:
            script['src'] = adjusted_path 
      markup=unicode(htmltree)

    #save the contents of the page locally.
    current_host, current_path = self._get_host_and_path(page_url)
    current_filepath, current_filename = self._get_local_location(current_host, current_path)
    self._create_dir(current_filepath)
    with open(os.path.join(current_filepath, current_filename), 'wb') as webfile:
      webfile.write(markup.encode('utf-8'))

      

  def _get_local_location(self, host, path):
    
    #Use regex maybe ?
    host = host.replace('https://', '').replace('http://', '')
    if path == '/':
      path = '/index.html'
    filepath, filename = os.path.split(os.path.join(self.root_dir, host + path))
    return filepath, filename


  def _get_standard_url(self, url):
    host, path = self._get_host_and_path(url)
    return host + path

  def _get_host_and_path(self,url):
    #Ignores query param, fragment and standardizes the end slash to uniquely identify a URL
    url_obj = urlparse(url)
    scheme = url_obj.scheme or 'http'
    if len(url_obj.path) > 1 and url_obj.path.endswith('/'):
      path = url_obj.path[:-1]
    elif url_obj.path == '':
      path = '/'
    else:
      path = url_obj.path
    host = (scheme + '://' + url_obj.hostname) if url_obj.hostname else None
    return host, path

  def _get_page(self, path):

    #requests library takes care of temporary and permanent redirections
    logger.info('Download page %s' % path)
    result = requests.get(path)
    if result.status_code == requests.codes.ok:
      return result
    else:
      #log the error and move on.
      logger.error('Failed to fetch %s: HTTP result code %s' % (path, result.status_code))
      return None
    

  def _create_dir(self, path):
    if not os.path.isdir(path):
      try:
        os.makedirs(path)
      except OSError as ex:
        if ex.errno != errno.EEXIST:
            raise


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="clone website options")

  parser.add_argument('-w', '--website-urls', required=True, nargs='+', help="List of websites which needs to be cloned.")
  parser.add_argument('-e', '--external-url', dest='external_url', action='store_true',
                      help="Fetch pages which are not in the domain of the website being cloned.")
  parser.add_argument('-d', '--directory', 
                      help="Directory in which the websites should be cloned. Defaults to current directory.")
  parser.set_defaults(external_url=False)

  args=parser.parse_args()

  cloner = Cloner(external_url=args.external_url, directory=args.directory,
   websites=args.website_urls)
  logger.info('Starting Clone Job...')
  cloner.go()
  logger.info('Ending Clone Job....')

