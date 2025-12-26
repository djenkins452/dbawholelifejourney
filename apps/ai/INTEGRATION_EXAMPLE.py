"""
Example: How to integrate AI insights into the dashboard view.

Add this to your existing DashboardView.get_context_data() method.
"""

# In apps/dashboard/views.py, add to get_context_data():

def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    user = self.request.user
    prefs = user.preferences
    
    # ... existing code ...
    
    # Add AI insights (new code)
    if getattr(settings, 'OPENAI_API_KEY', None):
        try:
            from apps.ai.dashboard_ai import get_dashboard_insight
            context['ai_insights'] = get_dashboard_insight(user)
        except Exception as e:
            # Gracefully handle AI failures
            context['ai_insights'] = {'available': False}
    else:
        context['ai_insights'] = {'available': False}
    
    return context


# =============================================================================
# Example template snippet for dashboard/home.html
# =============================================================================

"""
{% if ai_insights.available and ai_insights.daily_insight %}
<section class="ai-insight-card">
    <div class="ai-insight-header">
        <svg class="ai-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4M12 8h.01"/>
        </svg>
        <span class="ai-label">Daily Insight</span>
    </div>
    <p class="ai-insight-text">{{ ai_insights.daily_insight }}</p>
</section>
{% endif %}
"""

# =============================================================================
# Example CSS for the AI insight card
# =============================================================================

"""
.ai-insight-card {
    background: linear-gradient(135deg, 
        color-mix(in srgb, var(--color-accent) 5%, transparent) 0%, 
        var(--color-surface) 100%);
    border: 1px solid var(--color-border);
    border-left: 3px solid var(--color-accent);
    border-radius: var(--radius-lg);
    padding: var(--space-4);
    margin-bottom: var(--space-4);
}

.ai-insight-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
}

.ai-icon {
    width: 16px;
    height: 16px;
    color: var(--color-accent);
}

.ai-label {
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-muted);
}

.ai-insight-text {
    margin: 0;
    line-height: var(--line-height-relaxed);
    color: var(--color-text);
}
"""
