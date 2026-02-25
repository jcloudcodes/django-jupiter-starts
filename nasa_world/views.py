#views.py created 
from django.views.generic import TemplateView

class dashBoard(TemplateView):
    template_name = "index.html"
#Add in the 4th video
class TestPage(TemplateView):
    template_name = 'test.html'

class ThanksPage(TemplateView):
    template_name = 'thanks.html'
