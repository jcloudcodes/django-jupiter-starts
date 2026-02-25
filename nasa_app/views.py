# from django.shortcuts import render
from django.contrib.auth import login, logout
#from django.core.urlresolvers import reverse_lazy
from django.urls import reverse_lazy
from django.views.generic import CreateView

from . import forms

# Create your views here.
class SignUp(CreateView):
    form_class = forms.UserCreateForm
    #success_url = reverse_lazy("login")
    success_url = reverse_lazy("nasa_app:login")
    template_name = "nasa_app/signup.html"

