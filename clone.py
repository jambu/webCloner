import os, re
import argparse
import html5lib
from bs4 import BeautifulSoup
import errno
import requests,tinycss
from urlparse import urlparse, urljoin
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)


def get_urls_from_css_rules(rules):
  for r in rules:
    if type(r) == tinycss.css21.MediaRule:
      for r1 in get_urls_from_css_rules(r.rules):
        yield r1
      continue
    if type(r) == tinycss.css21.ImportRule:
      yield r.uri
      continue

    for d in r.declarations:
      for tok in d.value:
        if tok.type == 'URI':
          yield tok.value

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
    self.fetch_static = kwargs['fetch_static']
    self.urls_queue = []

  def go(self):
    
    for website in self.websites:
      if website.find('http') == -1: #Protocol not added to user input.
        website = '//' + website

      # There may be several redirects causing the program to throw an exception.
      website = self._get_final_url_after_redirection(website)
      logger.info('Cloning website %s....' % website)
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

    #Important step since redirects will cause the base url to change.
    page_url = result.url

    markup = result.text
    file_content = None
    content_type = result.headers['content-type']

    def process_link(attr, full_url_needed=False):
      
      absolute_url = urljoin(page_url, attr)

      #This is used for the case where links in the external page cannot be processed, 
      #however the link has to be changed to absolute url
      if full_url_needed:
        return absolute_url

      host, path = self._get_host_and_path(absolute_url)
      if not host:
        logger.warn('No host for path %s. Ignoring Endpoint' % path)
        return None
      is_external_url = page_url.find(host) == -1
      if is_external_url and not self.external_url: #External URL
        return None


      self.urls_queue.append(host+path)
      filepath, filename = self._get_local_location(host, path)  
      
      #This step replaces the url in the page with the standardized url. 
      #Usually static assets are served from a different server to prevent cookie transport for static assets.
      #Since we are storing everything locally, we need to rewrite all the urls and create directory structure
      #for storing external domain urls as well.
      return os.path.join(filepath, filename)
      
      #If a HTTP server is running in the local, we can avoid absolute file system paths, this can be made as a option as well.
      #return path

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
          link['href'] = adjusted_path 
      for script in htmltree.select('script[src]'):
        adjusted_path = process_link(script['src'])
        if adjusted_path:
            script['src'] = adjusted_path
      if self.fetch_static:
        for img in htmltree.select('img[src]'):
          adjusted_path = process_link(img['src'])
          if adjusted_path:
            img['src'] = adjusted_path
      file_content=unicode(htmltree)

    if self.fetch_static and content_type.find('text/css') == 0: #Process CSS files for more resources to download
      parser = tinycss.make_parser()
      rules = parser.parse_stylesheet(markup).rules
      for url in get_urls_from_css_rules(rules):
        adjusted_path = process_link(url)
        if adjusted_path:
          markup = markup.replace(url, adjusted_path)
      file_content = markup

    if file_content:
      file_content = file_content.encode('utf-8')
    else:
      file_content = result.content

    #save the contents of the page locally.
    current_host, current_path = self._get_host_and_path(page_url)
    current_filepath, current_filename = self._get_local_location(current_host, current_path)
    self._create_dir(current_filepath)
    with open(os.path.join(current_filepath, current_filename), 'wb') as webfile:
      webfile.write(file_content)

      

  def _get_local_location(self, host, path):
    
    #Use regex maybe ?
    host = host.replace('https://', '').replace('http://', '')
    if path == '/':
      path = '/index.html'
    filepath, filename = os.path.split(os.path.join(self.root_dir, host + path))
    #logger.info('localpath %s' % os.path.join(filepath, filename))
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

  def _get_page(self, fullpath):

    host, path = self._get_host_and_path(fullpath)

    filepath, filename = self._get_local_location(host, path)
    if os.path.exists(os.path.join(filepath, filename)): # Already processed URL
      logger.info('hit for existing local page %s' % os.path.join(filepath, filename))
      return None 

    #requests library takes care of temporary and permanent redirections
    logger.info('Downloading page %s' % fullpath)
    result = requests.get(fullpath)
    if result.status_code == requests.codes.ok:
      return result
    else:
      #log the error and move on.
      logger.error('Failed to fetch %s: HTTP result code %s' % (fullpath, result.status_code))
      return None

  def _get_final_url_after_redirection(self, path):
    return requests.get(self._get_standard_url(path)).url
    

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
  parser.add_argument('-s', '--fetch-static', dest='fetch_static', action='store_true',
                      help='Download resources which are referenced in css files and image tags locally.')
  parser.set_defaults(external_url=False)
  parser.set_defaults(fetch_static=False)

  args=parser.parse_args()

  cloner = Cloner(external_url=args.external_url, directory=args.directory,
   websites=args.website_urls, fetch_static=args.fetch_static)
  logger.info('Starting Clone Job...')
  cloner.go()
  logger.info('Ending Clone Job....')

