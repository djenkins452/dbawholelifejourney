"""Sports Domain — URL routing."""
from django.urls import path

from apps.sports import views

app_name = "sports"

urlpatterns = [
    path("", views.SportsHubView.as_view(), name="hub"),
    path("teams/", views.TeamSelectView.as_view(), name="team_select"),
    path("teams/follow/", views.FollowTeamView.as_view(), name="follow_team"),
    path("teams/unfollow/<int:pk>/", views.UnfollowTeamView.as_view(), name="unfollow_team"),
]
