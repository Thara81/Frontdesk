from django import forms

from accounts.models import User
from tickets.models import Category, Ticket


class StyledMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-select" if isinstance(field.widget, forms.Select) else "form-control")


class TicketCreateForm(StyledMixin, forms.Form):
    customer_name = forms.CharField(max_length=120)
    customer_email = forms.EmailField()
    phone = forms.CharField(max_length=20, required=False)
    company = forms.CharField(max_length=120, required=False)
    subject = forms.CharField(max_length=200)
    description = forms.CharField(widget=forms.Textarea)
    category = forms.ModelChoiceField(queryset=Category.objects.filter(is_active=True))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from tickets.constants import Priority
        self.fields["priority"] = forms.ChoiceField(choices=Priority.choices, widget=forms.Select(attrs={"class": "form-select"}))


class CommentForm(StyledMixin, forms.Form):
    body = forms.CharField(widget=forms.Textarea)
    visibility = forms.ChoiceField(choices=(("public", "Public reply"), ("internal", "Internal note")))


class AssignForm(StyledMixin, forms.Form):
    agent = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True, role=User.Role.AGENT))


class StatusForm(StyledMixin, forms.Form):
    status = forms.CharField()
