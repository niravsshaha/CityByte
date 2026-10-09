from django.urls import path  # noqa: F401  (kept so new info API routes can be added here)

# Place photos now come straight from Wikimedia Commons, so the old
# /api/info/place/photo proxy (which needed a Foursquare key) is gone.
urlpatterns = []
