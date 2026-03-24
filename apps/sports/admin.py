"""Sports Domain — Django admin registration."""
from django.contrib import admin

from apps.sports.models import GameEvent, League, Sport, Team, UserTeamFollow


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("abbreviation", "name", "sport", "is_college")
    list_filter = ("sport", "is_college")
    prepopulated_fields = {"slug": ("abbreviation",)}


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("full_name", "abbreviation", "league")
    list_filter = ("league",)
    search_fields = ("name", "location", "abbreviation")

    def full_name(self, obj):
        return obj.full_name


@admin.register(GameEvent)
class GameEventAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "home_score", "away_score", "start_time")
    list_filter = ("status", "home_team__league")
    date_hierarchy = "start_time"


@admin.register(UserTeamFollow)
class UserTeamFollowAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "priority", "is_active")
    list_filter = ("priority", "is_active")
    raw_id_fields = ("user", "team")
