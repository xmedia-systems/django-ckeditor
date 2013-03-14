import os
import re
from urlparse import urlparse, urlunparse, urljoin 
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext
from urllib import pathname2url

try:
    from PIL import Image, ImageOps
except ImportError:
    import Image
    import ImageOps

try:
    from django.views.decorators.csrf import csrf_exempt
except ImportError:
    # monkey patch this with a dummy decorator which just returns the
    # same function (for compatability with pre-1.1 Djangos)
    def csrf_exempt(fn):
        return fn

THUMBNAIL_SIZE = (75, 75)

CKEDITOR_STORAGE = getattr(settings, "CKEDITOR_STORAGE", None)
from django.core.files.storage import get_storage_class
CKEditorStorage = (get_storage_class(CKEDITOR_STORAGE))()
    


def get_thumb_filename(file_name):
    """
    Generate thumb filename by adding _thumb to end of
    filename before . (if present)
    """
    return '%s_thumb%s' % os.path.splitext(file_name)


def create_thumbnail(filename):
    image = Image.open(filename)

    # Convert to RGB if necessary
    # Thanks to Limodou on DjangoSnippets.org
    # http://www.djangosnippets.org/snippets/20/
    if image.mode not in ('L', 'RGB'):
        image = image.convert('RGB')

    # scale and crop to thumbnail
    imagefit = ImageOps.fit(image, THUMBNAIL_SIZE, Image.ANTIALIAS)
    imagefit.save(get_thumb_filename(filename))


def get_relative_url_from_path(prefix, path):
    relative_url = pathname2url(path)
    if relative_url[0] == '/':
        relative_url = relative_url[1:]
    return urljoin(prefix, relative_url)


def get_media_url(path):
    """
    Determine system file's media URL.
    """    
    upload_prefix = getattr(settings, "CKEDITOR_UPLOAD_PREFIX", None)
    if upload_prefix:
        url = get_relative_url_from_path(upload_prefix,
                                         os.path.relpath(path, settings.CKEDITOR_UPLOAD_PATH))
    else:
        url = get_relative_url_from_path(settings.MEDIA_URL, 
                                         os.path.relpath(path, settings.MEDIA_ROOT))

    # Remove multiple forward-slashes from the path portion of the url.
    # Break url into a list.
    url_parts = list(urlparse(url))
    # Replace two or more slashes with a single slash.
    url_parts[2] = re.sub('\/+', '/', url_parts[2])
    # Reconstruct the url.
    url = urlunparse(url_parts)

    return url


def get_upload_filename(upload_name, user):
    # If CKEDITOR_RESTRICT_BY_USER is True upload file to user specific path.
    if getattr(settings, 'CKEDITOR_RESTRICT_BY_USER', False):
        user_path = user.username
    else:
        user_path = ''

    # Generate date based path to put uploaded file.
    date_path_parts = datetime.now().strftime('%Y/%m/%d').split('/')

    # Complete upload path (upload_path + date_path).
    upload_path = os.path.join(settings.CKEDITOR_UPLOAD_PATH, user_path, \
            *date_path_parts)

    # Get available name and return.
    return os.path.join(upload_path, upload_name.lower())


@csrf_exempt
def upload(request):
    """
    Uploads a file and send back its URL to CKEditor.

    TODO:
        Validate uploads
    """
    # Get the uploaded file from request.
    upload = request.FILES['upload']
    
    #upload_ext = os.path.splitext(upload.name)[1]
    #security considerations

    # Open output file in which to store upload.
    upload_filename = get_upload_filename(upload.name, request.user)
    
    upload_filename = CKEditorStorage.save(upload_filename, upload)

    create_thumbnail(upload_filename)

    # Respond with Javascript sending ckeditor upload url.
    url = get_media_url(upload_filename)
    return HttpResponse("""
    <script type='text/javascript'>
        window.parent.CKEDITOR.tools.callFunction(%s, '%s');
    </script>""" % (request.GET['CKEditorFuncNum'], url))

def get_image_files(user=None):
    """
    Recursively walks all dirs under upload dir and generates a list of
    full paths for each file found.
    """
    # If a user is provided and CKEDITOR_RESTRICT_BY_USER is True,
    # limit images to user specific path, but not for superusers.
    if user and not user.is_superuser and getattr(settings, \
            'CKEDITOR_RESTRICT_BY_USER', False):
        user_path = user.username
    else:
        user_path = ''

    browse_path = os.path.join(settings.CKEDITOR_UPLOAD_PATH, user_path)

    for root, dirs, files in os.walk(browse_path):
        for filename in [os.path.join(root, x) for x in files]:
            # bypass for thumbs
            if os.path.splitext(filename)[0].endswith('_thumb'):
                continue
            yield filename

def get_image_browse_urls(user=None):
    """
    Recursively walks all dirs under upload dir and generates a list of
    thumbnail and full image URL's for each file found.
    """
    images = []
    for filename in get_image_files(user=user):
        images.append({
            'thumb': get_media_url(get_thumb_filename(filename)),
            'src': get_media_url(filename)
        })

    return images


def browse(request):
    context = RequestContext(request, {
        'images': get_image_browse_urls(request.user),
    })
    return render_to_response('browse.html', context)
