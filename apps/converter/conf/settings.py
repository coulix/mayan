from django.conf import settings
from django.utils.translation import ugettext_lazy as _


CONVERT_PATH = getattr(settings, 'CONVERTER_CONVERT_PATH', u'/usr/bin/convert')
UNPAPER_PATH = getattr(settings, 'CONVERTER_UNPAPER_PATH', u'/usr/bin/unpaper')
IDENTIFY_PATH = getattr(settings, 'CONVERTER_IDENTIFY_PATH', u'/usr/bin/identify')
OCR_OPTIONS = getattr(settings, 'CONVERTER_OCR_OPTIONS', u'-colorspace Gray -depth 8 -resample 200x200')
DEFAULT_OPTIONS = getattr(settings, 'CONVERTER_DEFAULT_OPTIONS', u'')
LOW_QUALITY_OPTIONS = getattr(settings, 'CONVERTER_LOW_QUALITY_OPTIONS', u'')
HIGH_QUALITY_OPTIONS = getattr(settings, 'CONVERTER_HIGH_QUALITY_OPTIONS', u'-density 400')


setting_description = {
    'CONVERTER_CONVERT_PATH':_(u'File path to imagemagick\'s convert program.'),
    'CONVERTER_IDENTIFY_PATH':_(u'File path to imagemagick\'s identify program.'),
    'CONVERTER_UNPAPER_PATH':_(u'File path to unpaper program.'),
}
