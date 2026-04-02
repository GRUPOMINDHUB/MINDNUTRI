from django.shortcuts import render


def home(request):
    return render(request, "home.html")


def mindnutri_landing(request):
    return render(request, "mindnutri_landing.html")
