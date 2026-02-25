#from django.conf.urls import url
from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

app_name = 'nasa_app'

urlpatterns = [
    #url(r"login/$", auth_views.LoginView.as_view(template_name="accounts/login.html"),name='login'),
    path("login/", auth_views.LoginView.as_view(template_name="nasa_app/login.html"), name="login"),
    #url(r"logout/$", auth_views.LogoutView.as_view(), name="logout"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    #url(r"signup/$", views.SignUp.as_view(), name="signup"),
    path("signup/", views.SignUp.as_view(), name="signup"),
    #part 12 debugging adding posts
    #Your nasa_app app should only handle auth/signup pages. Remove this line:below
    #path("posts/", include(("posts.urls", "posts"), namespace="posts")),
    #path("groups/", include(("groups.urls", "groups"), namespace="groups")),

]