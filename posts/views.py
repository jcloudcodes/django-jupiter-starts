from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.urls import reverse_lazy
from django.views import generic

from . import models
from django.contrib.auth import get_user_model

User = get_user_model()


class PostList(generic.ListView):
    model = models.Post

    def get_queryset(self):
        return models.Post.objects.select_related("user", "group")


class UserPosts(generic.ListView):
    model = models.Post
    template_name = "posts/user_post_list.html"

    def get_queryset(self):
        try:
            self.post_user = User.objects.get(username__iexact=self.kwargs.get("username"))
        except User.DoesNotExist:
            raise Http404
        return (
            models.Post.objects
            .select_related("user", "group")
            .filter(user=self.post_user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["post_user"] = self.post_user
        return context


class PostDetail(generic.DetailView):
    model = models.Post

    def get_queryset(self):
        return (
            models.Post.objects
            .select_related("user", "group")
            .filter(user__username__iexact=self.kwargs.get("username"))
        )


class CreatePost(LoginRequiredMixin, generic.CreateView):
    model = models.Post
    fields = ("message", "group")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()
        return super().form_valid(form)


class DeletePost(LoginRequiredMixin, generic.DeleteView):
    model = models.Post
    success_url = reverse_lazy("posts:all")

    def get_queryset(self):
        return models.Post.objects.filter(user_id=self.request.user.id)

    def form_valid(self, form):
        messages.success(self.request, "Post Deleted")
        return super().form_valid(form)