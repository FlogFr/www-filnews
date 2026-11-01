from django.conf import settings
from django.utils import timezone


def site(request):
    return {
        "SITE_URL": settings.SITE_URL,
        "SITE_NAME": settings.SITE_NAME,
        "SITE_TAGLINE": settings.SITE_TAGLINE,
        "current_year": timezone.now().year,
    }
