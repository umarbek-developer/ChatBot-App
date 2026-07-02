from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.include_root_view = False

urlpatterns = [

    # path('', include(router.urls)),
    # path('restaurant/', RestaurantViewset.as_view({'get': 'list','post':'create'}), name='restaurant-detail'),
]
