"""
URL configuration for nasa_world project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Home page
    path("", views.dashBoard.as_view(), name="home"),

    # App URLs
    #path 3
    path("nasa_app/", include(("nasa_app.urls", "nasa_app"), namespace="nasa_app")),
    path(
    "accounts/login/",
    auth_views.LoginView.as_view(template_name="nasa_app/login.html"),
    name="login"
    ),
    #overridate djangot login
    path("accounts/", include("django.contrib.auth.urls")),

    # ✅ ADD THESE (this registers the namespaces)
    path("posts/", include(("posts.urls", "posts"), namespace="posts")),
    path("groups/", include(("groups.urls", "groups"), namespace="groups")),

    # Extra pages
    path("test/", views.TestPage.as_view(), name="test"),
    path("thanks/", views.ThanksPage.as_view(), name="thanks"),
]
