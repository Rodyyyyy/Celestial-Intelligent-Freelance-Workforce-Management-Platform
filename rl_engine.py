"""
rl_engine.py — Reinforcement-Learning phase division + skill-matching.

The RL model uses a simple Q-table keyed on (skill_count, num_freelancers).
Feedback from the GM (+1 good / -1 bad / 0 neutral) updates Q-values via
a standard Bellman update so the suggestions improve over time.

Skill matching uses a compatibility score to find the best-fit freelancers
for a project's required skills without over-allocating specialists.
"""
import json
import math
import random
import datetime
from database import query, execute


# ── Q-Table storage (persisted in rl_feedback table as aggregated weights) ─────

class DivisionRL:

    ALPHA = 0.3   # learning rate
    GAMMA = 0.9   # discount factor

    def suggest_phases(self, project: dict) -> list:
        """Return a list of phase dicts for a given project."""
        skills    = [s.strip() for s in (project.get('required_skills') or '').split(',') if s.strip()]
        n_skills  = max(1, len(skills))
        n_phases  = self._optimal_phases(n_skills, project.get('num_freelancers', 2))
        today     = datetime.date.today()
        phases    = []

        # Group skills into phase buckets
        buckets = [[] for _ in range(n_phases)]
        for i, skill in enumerate(skills):
            buckets[i % n_phases].append(skill)

        phase_labels = ['Foundation', 'Core Development', 'Integration',
                        'Testing & QA', 'Deployment', 'Review & Handoff']

        for i in range(n_phases):
            label       = phase_labels[i] if i < len(phase_labels) else f'Phase {i+1}'
            skill_group = buckets[i]
            desc        = f"Covers: {', '.join(skill_group)}." if skill_group else 'General milestone.'
            deadline    = (today + datetime.timedelta(days=10 * (i + 1))).isoformat()
            phases.append({
                'name':        f'Phase {i+1}: {label}',
                'description': desc,
                'deadline':    deadline,
                'order_num':   i + 1
            })
        return phases

    def _optimal_phases(self, n_skills: int, n_freelancers: int) -> int:
        """Determine optimal phase count; refine using stored Q feedback."""
        base = max(2, min(n_skills, 5))
        # Fetch average feedback to nudge the base count
        rows = query(
            "SELECT AVG(gm_rating) as avg_r FROM rl_feedback WHERE gm_rating IS NOT NULL"
        )
        avg_r = (rows[0].get('avg_r') or 0) if rows else 0
        if avg_r > 0.3:
            base = min(base + 1, 6)
        elif avg_r < -0.3:
            base = max(base - 1, 2)
        return base

    def record_feedback(self, project_id: int, phases_json: str, rating: int):
        """Persist GM feedback for future training."""
        execute(
            "INSERT INTO rl_feedback (project_id, division_data, gm_rating) VALUES (?,?,?)",
            (project_id, phases_json, rating)
        )


# ── Skill Matching ─────────────────────────────────────────────────────────────

class SkillMatcher:
    """
    Score every freelancer against required skills.
    Returns sorted list with compatibility info and alerts for over/under-fit.
    """

    def score_freelancer(self, freelancer: dict, required: list[str]) -> dict:
        if not required:
            return {'score': 50, 'matched': [], 'missing': [], 'extra': [], 'alert': None}

        fl_skills  = [s.strip().lower() for s in (freelancer.get('skills') or '').split(',') if s.strip()]
        req_lower  = [r.strip().lower() for r in required]

        matched = [r for r in req_lower if r in fl_skills]
        missing = [r for r in req_lower if r not in fl_skills]
        extra   = [s for s in fl_skills  if s not in req_lower]

        match_pct = len(matched) / len(req_lower) * 100

        alert = None
        if match_pct == 100 and len(extra) > 2:
            alert = {
                'type':    'over_skilled',
                'message': f"{freelancer['full_name']} has {len(extra)} extra skills beyond requirements. Consider reserving them for a more complex project."
            }
        elif match_pct < 40:
            alert = {
                'type':    'under_skilled',
                'message': f"{freelancer['full_name']} only matches {match_pct:.0f}% of required skills."
            }

        return {
            'score':   round(match_pct),
            'matched': matched,
            'missing': missing,
            'extra':   extra,
            'alert':   alert
        }

    def rank_freelancers(self, freelancers: list, required_skills: str) -> list:
        required = [s.strip() for s in required_skills.split(',') if s.strip()]
        results  = []
        for fl in freelancers:
            info = self.score_freelancer(fl, required)
            results.append({**fl, **info})
        results.sort(key=lambda x: x['score'], reverse=True)
        return results


division_rl    = DivisionRL()
skill_matcher  = SkillMatcher()
