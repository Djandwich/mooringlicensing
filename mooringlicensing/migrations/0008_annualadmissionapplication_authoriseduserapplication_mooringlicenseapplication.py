# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2021-03-09 07:05
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mooringlicensing', '0007_auto_20210309_1431'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnnualAdmissionApplication',
            fields=[
                ('proposal', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='mooringlicensing.Proposal')),
            ],
            bases=('mooringlicensing.proposal',),
        ),
        migrations.CreateModel(
            name='AuthorisedUserApplication',
            fields=[
                ('proposal', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='mooringlicensing.Proposal')),
            ],
            bases=('mooringlicensing.proposal',),
        ),
        migrations.CreateModel(
            name='MooringLicenseApplication',
            fields=[
                ('proposal', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='mooringlicensing.Proposal')),
            ],
            bases=('mooringlicensing.proposal',),
        ),
    ]
