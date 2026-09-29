from django.contrib import admin
from django.urls import path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

from iph import views


urlpatterns = [

    # ============================================================
    # LOGIN
    # ============================================================

    path(
        "",
        views.login_view,
        name="login",
    ),

    path(
        "login/",
        views.login_view,
        name="login_page",
    ),


    # ============================================================
    # REGISTER
    # ============================================================

    path(
        "register/",
        views.register_view,
        name="register",
    ),

    # ============================================================
    # GOOGLE LOGIN
    # ============================================================

    path(
        "accounts/google/login/",
        views.google_login,
        name="google",
    ),

    path(
        "accounts/google/callback/",
        views.google_callback,
        name="google_callback",
    ),

    # ============================================================
    # LUPA PASSWORD
    # ============================================================

    path(
        "lupa-password/",
        auth_views.PasswordResetView.as_view(
            template_name="iph/password_reset.html"
        ),
        name="password_reset",
    ),

    path(
        "lupa-password/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="iph/password_reset_done.html"
        ),
        name="password_reset_done",
    ),  

    path(
        "reset-password/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="iph/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),

    path(   
        "reset-password/selesai/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="iph/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),

    # ============================================================
    # HOME / BERANDA
    # ============================================================

    path(
        "home/",
        views.home_view,
        name="home",
    ),


    # ============================================================
    # DASHBOARD
    # ============================================================

    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),


    # ============================================================
    # UPLOAD DATA
    # ============================================================

    path(
        "upload/",
        views.upload_data,
        name="upload",
    ),


    # ============================================================
    # ANALISIS
    # ============================================================

    path(
        "analisis/",
        views.analisis,
        name="analisis",
    ),


    # ============================================================
    # GENERATE INFOGRAFIS
    # ============================================================

    path(
        "generate/",
        views.generate_view,
        name="generate",
    ),


    # ============================================================
    # LOGOUT
    # ============================================================

    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),


]


# ============================================================
# MEDIA FILES
# ============================================================

if settings.DEBUG:

    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )