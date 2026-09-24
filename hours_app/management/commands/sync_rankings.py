import pandas as pd
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from hours_app.models import CheckInOut

class Command(BaseCommand):
    help = 'Imports hours from Robotics Attendance 2026 (Responses).xlsx'

    def handle(self, *args, **options):
        # The exact file name you provided
        file_path = "Robotics Attendance 2026 (Responses).xlsx"
        
        try:
            # usecols=[0, 2] ignores Column B (Sum) and takes Column A (Email) and C (Hours)
            df = pd.read_excel(file_path, usecols=[0, 2], names=['Email', 'Hours'])
            
            success_count = 0
            missing_users = []

            for _, row in df.iterrows():
                email_input = str(row['Email']).strip()
                hours_value = row['Hours']

                # Skip if hours are missing or not a number
                if pd.isna(hours_value):
                    continue

                # Case-insensitive search to prevent capitalization errors
                user = User.objects.filter(email__iexact=email_input).first()
                
                if user:
                    # Create a finished session to update the rankings
                    CheckInOut.objects.create(
                        user=user,
                        check_in_time=timezone.now() - timedelta(hours=float(hours_value)),
                        check_out_time=timezone.now(),
                        reason="Terminal Sync: Robotics 2026"
                    )
                    success_count += 1
                else:
                    missing_users.append(email_input)

            self.stdout.write(self.style.SUCCESS(f'Successfully imported {success_count} records!'))
            
            if missing_users:
                self.stdout.write(self.style.WARNING(f'The following emails were not found in the database: {set(missing_users)}'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'File "{file_path}" not found. Place it in the same folder as manage.py'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred: {e}'))