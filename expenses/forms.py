from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Choose a username", "autofocus": True})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com"})
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "At least 8 characters"})
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Re-enter your password"})
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def clean_email(self):
        """Reject registration if the email is already in use by another account."""
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ExpenseForm(forms.Form):
    title = forms.CharField(max_length=100)
    amount = forms.DecimalField(max_digits=10, decimal_places=2)
    category = forms.ChoiceField(choices=[
        ("Food", "Food"),
        ("Transport", "Transport"),
        ("Shopping", "Shopping"),
        ("Bills", "Bills"),
        ("Other", "Other"),
    ])
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    is_recurring = forms.BooleanField(
        required=False,
        label="This is a recurring monthly expense (e.g. rent, subscription)"
    )

class EditProfileForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    photo = forms.ImageField(required=False)


class ReceiptUploadForm(forms.Form):
    receipt = forms.ImageField()


class BudgetForm(forms.Form):
    monthly_budget = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0,
        label="Monthly Budget (₹)"
    )


class SplitExpenseForm(forms.Form):
    friend_username = forms.CharField(max_length=150, label="Friend's Username")
    title = forms.CharField(max_length=100)
    total_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01, label="Total Amount (₹)")
    category = forms.ChoiceField(choices=[
        ("Food", "Food"),
        ("Transport", "Transport"),
        ("Shopping", "Shopping"),
        ("Bills", "Bills"),
        ("Other", "Other"),
    ])
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))