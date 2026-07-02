import django_filters


# class ProductFilter(django_filters.FilterSet):
#     category = django_filters.CharFilter(field_name='category__title_uz', lookup_expr='icontains')
#     title = django_filters.CharFilter(field_name='title_uz', lookup_expr='icontains')

#     class Meta:
#         model = Product
#         fields = ['category', 'title']