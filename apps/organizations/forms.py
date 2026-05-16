from django import forms


class OrganizationSearchForm(forms.Form):
    """Simple search/filter form for the public organization directory."""

    q = forms.CharField(
        required=False,
        label='Search',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by name or address'}),
    )
    type = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        choices=[
            ('', 'All types'),
            ('hospital', 'Hospital'),
            ('bank', 'Bank'),
            ('govt', 'Government'),
        ],
    )
