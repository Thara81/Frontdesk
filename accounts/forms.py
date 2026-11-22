from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from accounts.models import User


class StyledFormMixin:
    def _style(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                continue
            css = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs.setdefault("class", css)


class EmployeeAuthenticationForm(StyledFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
        self.fields["username"].widget.attrs["placeholder"] = "Username"
        self.fields["password"].widget.attrs["placeholder"] = "Password"

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_employee:
            raise forms.ValidationError("This portal is for support staff.", code="no_employee")


class EmployeeCreateForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "phone", "job_title", "password"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.is_staff = user.role == User.Role.ADMIN
        if commit:
            user.save()
        return user


class EmployeeUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "phone", "job_title", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = user.role == User.Role.ADMIN or user.is_superuser
        if commit:
            user.save()
        return user


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "job_title"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
