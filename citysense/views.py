from django.shortcuts import render

def home(request):
    """
    Renders the CitySense landing page along with sample context data
    for testing Phase 1 reusable frontend components.
    """
    sample_issues = [
        {
            'title': 'Severe Pothole on Main Arterial Avenue',
            'description': 'Deep pothole causing traffic congestion and potential vehicle damage near the central intersection.',
            'category': 'Pothole',
            'priority': 'HIGH',
            'status': 'VERIFIED',
            'department': 'Road Maintenance',
            'location': 'Downtown Sector 4',
            'time_ago': '2 hours ago',
            'duplicate_count': 3,
        },
        {
            'title': 'Uncollected Garbage Accumulation',
            'description': 'Overflowing municipal waste bins spilling onto sidewalk near market area.',
            'category': 'Garbage',
            'priority': 'MEDIUM',
            'status': 'IN_PROGRESS',
            'department': 'Sanitation Department',
            'location': 'Green Park Ward 12',
            'time_ago': '5 hours ago',
            'duplicate_count': 1,
        },
        {
            'title': 'Broken Streetlight Grid',
            'description': 'Multiple streetlights non-operational creating safety concerns during night hours.',
            'category': 'Streetlight',
            'priority': 'CRITICAL',
            'status': 'ASSIGNED',
            'department': 'Electrical & Lighting',
            'location': 'North Ring Road',
            'time_ago': '1 day ago',
            'duplicate_count': 5,
        }
    ]

    context = {
        'sample_issues': sample_issues,
        'statuses': ['REPORTED', 'VERIFIED', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'REJECTED'],
        'priorities': ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
    }
    return render(request, 'landing/home.html', context)
