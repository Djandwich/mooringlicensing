import re
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from preserialize.serialize import serialize
from ledger.accounts.models import EmailUser #, Document
from mooringlicensing.components.proposals.models import (
        ProposalDocument, #ProposalPark, ProposalParkActivity, ProposalParkAccess, ProposalTrail, ProposalTrailSectionActivity, ProposalTrailSection, ProposalParkZone, ProposalParkZoneActivity, ProposalOtherDetails, ProposalAccreditation, 
        ProposalUserAction, 
        ProposalAssessment, 
        ProposalAssessmentAnswer, 
        ChecklistQuestion,
        ProposalStandardRequirement
        )
from mooringlicensing.components.approvals.models import Approval
from mooringlicensing.components.proposals.email import send_submit_email_notification, send_external_submit_email_notification
#from mooringlicensing.components.main.models import Activity, Park, AccessType, Trail, Section, Zone
import traceback
import os
from copy import deepcopy
from datetime import datetime
import time


import logging
logger = logging.getLogger(__name__)

def create_data_from_form(schema, post_data, file_data, post_data_index=None,special_fields=[],assessor_data=False):
    data = {}
    special_fields_list = []
    assessor_data_list = []
    comment_data_list = {}
    special_fields_search = SpecialFieldsSearch(special_fields)
    if assessor_data:
        assessor_fields_search = AssessorDataSearch()
        comment_fields_search = CommentDataSearch()
    try:
        for item in schema:
            data.update(_create_data_from_item(item, post_data, file_data, 0, ''))
            #_create_data_from_item(item, post_data, file_data, 0, '')
            special_fields_search.extract_special_fields(item, post_data, file_data, 0, '')
            if assessor_data:
                assessor_fields_search.extract_special_fields(item, post_data, file_data, 0, '')
                comment_fields_search.extract_special_fields(item, post_data, file_data, 0, '')
        special_fields_list = special_fields_search.special_fields
        if assessor_data:
            assessor_data_list = assessor_fields_search.assessor_data
            comment_data_list = comment_fields_search.comment_data
    except:
        traceback.print_exc()
    if assessor_data:
        return [data],special_fields_list,assessor_data_list,comment_data_list

    return [data],special_fields_list


def _extend_item_name(name, suffix, repetition):
    return '{}{}-{}'.format(name, suffix, repetition)

def _create_data_from_item(item, post_data, file_data, repetition, suffix):
    item_data = {}

    if 'name' in item:
        extended_item_name = item['name']
    else:
        raise Exception('Missing name in item %s' % item['label'])

    if 'children' not in item:
        if item['type'] in ['checkbox' 'declaration']:
            #item_data[item['name']] = post_data[item['name']]
            item_data[item['name']] = extended_item_name in post_data
        elif item['type'] == 'file':
            if extended_item_name in file_data:
                item_data[item['name']] = str(file_data.get(extended_item_name))
                # TODO save the file here
            elif extended_item_name + '-existing' in post_data and len(post_data[extended_item_name + '-existing']) > 0:
                item_data[item['name']] = post_data.get(extended_item_name + '-existing')
            else:
                item_data[item['name']] = ''
        else:
            if extended_item_name in post_data:
                if item['type'] == 'multi-select':
                    item_data[item['name']] = post_data.getlist(extended_item_name)
                else:
                    item_data[item['name']] = post_data.get(extended_item_name)
    else:
        if 'repetition' in item:
            item_data = generate_item_data(extended_item_name,item,item_data,post_data,file_data,len(post_data[item['name']]),suffix)
        else:
            item_data = generate_item_data(extended_item_name, item, item_data, post_data, file_data,1,suffix)


    if 'conditions' in item:
        for condition in item['conditions'].keys():
            for child in item['conditions'][condition]:
                item_data.update(_create_data_from_item(child, post_data, file_data, repetition, suffix))

    return item_data

def generate_item_data(item_name,item,item_data,post_data,file_data,repetition,suffix):
    item_data_list = []
    for rep in xrange(0, repetition):
        child_data = {}
        for child_item in item.get('children'):
            child_data.update(_create_data_from_item(child_item, post_data, file_data, 0,
                                                     '{}-{}'.format(suffix, rep)))
        item_data_list.append(child_data)

        item_data[item['name']] = item_data_list
    return item_data

class AssessorDataSearch(object):

    def __init__(self,lookup_field='canBeEditedByAssessor'):
        self.lookup_field = lookup_field
        self.assessor_data = []

    def extract_assessor_data(self,item,post_data):
        values = []
        res = {
            'name': item,
            'assessor': '',
            'referrals':[]
        }
        for k in post_data:
            if re.match(item,k):
                values.append({k:post_data[k]})
        if values:
            for v in values:
                for k,v in v.items():
                    parts = k.split('{}-'.format(item))
                    if len(parts) > 1:
                        # split parts to see if referall
                        ref_parts = parts[1].split('Referral-')
                        if len(ref_parts) > 1:
                            # Referrals
                            res['referrals'].append({
                                'value':v,
                                'email':ref_parts[1],
                                'full_name': EmailUser.objects.get(email=ref_parts[1].lower()).get_full_name()
                            })
                        elif k.split('-')[-1].lower() == 'assessor':
                            # Assessor
                            res['assessor'] = v

        return res

    def extract_special_fields(self,item, post_data, file_data, repetition, suffix):
        item_data = {}
        if 'name' in item:
            extended_item_name = item['name']
        else:
            raise Exception('Missing name in item %s' % item['label'])

        if 'children' not in item:
            if 'conditions' in item:
                for condition in item['conditions'].keys():
                    for child in item['conditions'][condition]:
                        item_data.update(self.extract_special_fields(child, post_data, file_data, repetition, suffix))

            if item.get(self.lookup_field):
                self.assessor_data.append(self.extract_assessor_data(extended_item_name,post_data))

        else:
            if 'repetition' in item:
                item_data = self.generate_item_data_special_field(extended_item_name,item,item_data,post_data,file_data,len(post_data[item['name']]),suffix)
            else:
                item_data = self.generate_item_data_special_field(extended_item_name, item, item_data, post_data, file_data,1,suffix)

            if 'conditions' in item:
                for condition in item['conditions'].keys():
                    for child in item['conditions'][condition]:
                        item_data.update(self.extract_special_fields(child, post_data, file_data, repetition, suffix))

        return item_data

    def generate_item_data_special_field(self,item_name,item,item_data,post_data,file_data,repetition,suffix):
        item_data_list = []
        for rep in xrange(0, repetition):
            child_data = {}
            for child_item in item.get('children'):
                child_data.update(self.extract_special_fields(child_item, post_data, file_data, 0,
                                                         '{}-{}'.format(suffix, rep)))
            item_data_list.append(child_data)

            item_data[item['name']] = item_data_list
        return item_data

class CommentDataSearch(object):

    def __init__(self,lookup_field='canBeEditedByAssessor'):
        self.lookup_field = lookup_field
        self.comment_data = {}

    def extract_comment_data(self,item,post_data):
        res = {}
        values = []
        for k in post_data:
            if re.match(item,k):
                values.append({k:post_data[k]})
        if values:
            for v in values:
                for k,v in v.items():
                    parts = k.split('{}'.format(item))
                    if len(parts) > 1:
                        ref_parts = parts[1].split('-comment-field')
                        if len(ref_parts) > 1:
                            res = {'{}'.format(item):v}
        return res

    def extract_special_fields(self,item, post_data, file_data, repetition, suffix):
        item_data = {}
        if 'name' in item:
            extended_item_name = item['name']
        else:
            raise Exception('Missing name in item %s' % item['label'])

        if 'children' not in item:
            self.comment_data.update(self.extract_comment_data(extended_item_name,post_data))

        else:
            if 'repetition' in item:
                item_data = self.generate_item_data_special_field(extended_item_name,item,item_data,post_data,file_data,len(post_data[item['name']]),suffix)
            else:
                item_data = self.generate_item_data_special_field(extended_item_name, item, item_data, post_data, file_data,1,suffix)


        if 'conditions' in item:
            for condition in item['conditions'].keys():
                for child in item['conditions'][condition]:
                    item_data.update(self.extract_special_fields(child, post_data, file_data, repetition, suffix))

        return item_data

    def generate_item_data_special_field(self,item_name,item,item_data,post_data,file_data,repetition,suffix):
        item_data_list = []
        for rep in xrange(0, repetition):
            child_data = {}
            for child_item in item.get('children'):
                child_data.update(self.extract_special_fields(child_item, post_data, file_data, 0,
                                                         '{}-{}'.format(suffix, rep)))
            item_data_list.append(child_data)

            item_data[item['name']] = item_data_list
        return item_data

class SpecialFieldsSearch(object):

    def __init__(self,lookable_fields):
        self.lookable_fields = lookable_fields
        self.special_fields = {}

    def extract_special_fields(self,item, post_data, file_data, repetition, suffix):
        item_data = {}
        if 'name' in item:
            extended_item_name = item['name']
        else:
            raise Exception('Missing name in item %s' % item['label'])

        if 'children' not in item:
            for f in self.lookable_fields:
                if item['type'] in ['checkbox' 'declaration']:
                    val = None
                    val = item.get(f,None)
                    if val:
                        item_data[f] = extended_item_name in post_data
                        self.special_fields.update(item_data)
                else:
                    if extended_item_name in post_data:
                        val = None
                        val = item.get(f,None)
                        if val:
                            if item['type'] == 'multi-select':
                                item_data[f] = ','.join(post_data.getlist(extended_item_name))
                            else:
                                item_data[f] = post_data.get(extended_item_name)
                            self.special_fields.update(item_data)
        else:
            if 'repetition' in item:
                item_data = self.generate_item_data_special_field(extended_item_name,item,item_data,post_data,file_data,len(post_data[item['name']]),suffix)
            else:
                item_data = self.generate_item_data_special_field(extended_item_name, item, item_data, post_data, file_data,1,suffix)


        if 'conditions' in item:
            for condition in item['conditions'].keys():
                for child in item['conditions'][condition]:
                    item_data.update(self.extract_special_fields(child, post_data, file_data, repetition, suffix))

        return item_data

    def generate_item_data_special_field(self,item_name,item,item_data,post_data,file_data,repetition,suffix):
        item_data_list = []
        for rep in xrange(0, repetition):
            child_data = {}
            for child_item in item.get('children'):
                child_data.update(self.extract_special_fields(child_item, post_data, file_data, 0,
                                                         '{}-{}'.format(suffix, rep)))
            item_data_list.append(child_data)

            item_data[item['name']] = item_data_list
        return item_data


def save_proponent_data(instance,request,viewset,parks=None,trails=None):
    if instance.application_type.name==ApplicationType.FILMING:
        save_proponent_data_filming(instance,request,viewset,parks=None,trails=None)
    elif instance.application_type.name==ApplicationType.EVENT:
        save_proponent_data_event(instance,request,viewset,parks=None,trails=None)
    else:
        save_proponent_data_tclass(instance,request,viewset,parks=None,trails=None)


#from mooringlicensing.components.main.models import ApplicationType

def save_assessor_data(instance,request,viewset):
    with transaction.atomic():
        try:
            pass
            #if instance.application_type.name==ApplicationType.FILMING:
            #    save_assessor_data_filming(instance,request,viewset)
            #if instance.application_type.name==ApplicationType.TCLASS:
            #    save_assessor_data_tclass(instance,request,viewset)
            #if instance.application_type.name==ApplicationType.EVENT:
            #    save_assessor_data_event(instance,request,viewset)            
        except:
            raise

# TODO: is this used or Proposal.submit() ?
def proposal_submit(proposal,request):
        with transaction.atomic():
            if proposal.can_user_edit:
                proposal.submitter = request.user
                #proposal.lodgement_date = datetime.datetime.strptime(timezone.now().strftime('%Y-%m-%d'),'%Y-%m-%d').date()
                proposal.lodgement_date = timezone.now()
                proposal.training_completed = True
                if (proposal.amendment_requests):
                    qs = proposal.amendment_requests.filter(status = "requested")
                    if (qs):
                        for q in qs:
                            q.status = 'amended'
                            q.save()

                # Create a log entry for the proposal
                proposal.log_user_action(ProposalUserAction.ACTION_LODGE_APPLICATION.format(proposal.id),request)
                # Create a log entry for the organisation
                #proposal.applicant.log_user_action(ProposalUserAction.ACTION_LODGE_APPLICATION.format(proposal.id),request)
                applicant_field=getattr(proposal, proposal.applicant_field)
                applicant_field.log_user_action(ProposalUserAction.ACTION_LODGE_APPLICATION.format(proposal.id),request)

                # print('requirement block')
                # default_requirements=ProposalStandardRequirement.objects.filter(application_type=proposal.application_type, default=True, obsolete=False)
                # print('default', default_requirements)
                # if default_requirements:
                #     for req in default_requirements:
                #         print ('req',req)
                #         try:
                #             r, created=ProposalRequirement.objects.get_or_create(proposal=proposal, standard_requirement=req)
                #             print(r, created, r.id)
                #         except:
                #             raise
        
                ret1 = send_submit_email_notification(request, proposal)
                ret2 = send_external_submit_email_notification(request, proposal)

                #proposal.save_form_tabs(request)
                if ret1 and ret2:
                    proposal.processing_status = 'with_assessor'
                    proposal.customer_status = 'with_assessor'
                    proposal.documents.all().update(can_delete=False)
                    proposal.required_documents.all().update(can_delete=False)
                    proposal.save()
                else:
                    raise ValidationError('An error occurred while submitting proposal (Submit email notifications failed)')
                #Create assessor checklist with the current assessor_list type questions
                #Assessment instance already exits then skip.
                try:
                    assessor_assessment=ProposalAssessment.objects.get(proposal=proposal,referral_group=None, referral_assessment=False)
                except ProposalAssessment.DoesNotExist:
                    assessor_assessment=ProposalAssessment.objects.create(proposal=proposal,referral_group=None, referral_assessment=False)
                    checklist=ChecklistQuestion.objects.filter(list_type='assessor_list', application_type=proposal.application_type, obsolete=False)
                    for chk in checklist:
                        try:
                            chk_instance=ProposalAssessmentAnswer.objects.get(question=chk, assessment=assessor_assessment)
                        except ProposalAssessmentAnswer.DoesNotExist:
                            chk_instance=ProposalAssessmentAnswer.objects.create(question=chk, assessment=assessor_assessment)

                return proposal

            else:
                raise ValidationError('You can\'t edit this proposal at this moment')


def is_payment_officer(user):
    from mooringlicensing.components.proposals.models import PaymentOfficerGroup
    try:
        group= PaymentOfficerGroup.objects.get(default=True)
    except PaymentOfficerGroup.DoesNotExist:
        group= None
    if group:
        if user in group.members.all():
            return True
    return False


#from mooringlicensing.components.proposals.models import (
#        Proposal, #Referral, 
#        AmendmentRequest, 
#        ProposalDeclinedDetails
#        )
#from mooringlicensing.components.approvals.models import Approval
#from mooringlicensing.components.compliances.models import Compliance
##from mooringlicensing.components.bookings.models import ApplicationFee, Booking
#from ledger.payments.models import Invoice
#from mooringlicensing.components.proposals import email as proposal_email
#from mooringlicensing.components.approvals import email as approval_email
#from mooringlicensing.components.compliances import email as compliance_email
#from mooringlicensing.components.bookings import email as booking_email
#def test_proposal_emails(request):
#    """ Script to test all emails (listed below) from the models """
#    # setup
#    if not (settings.PRODUCTION_EMAIL):
#        recipients = [request.user.email]
#        #proposal = Proposal.objects.last()
#        approval = Approval.objects.filter(migrated=False).last()
#        proposal = approval.current_proposal
#        referral = Referral.objects.last()
#        amendment_request = AmendmentRequest.objects.last()
#        reason = 'Not enough information'
#        proposal_decline = ProposalDeclinedDetails.objects.last()
#        compliance = Compliance.objects.last()
#
#        application_fee = ApplicationFee.objects.last()
#        api = Invoice.objects.get(reference=application_fee.application_fee_invoices.last().invoice_reference)
#
#        booking = Booking.objects.last()
#        bi = Invoice.objects.get(reference=booking.invoices.last().invoice_reference)
#
#        proposal_email.send_qaofficer_email_notification(proposal, recipients, request, reminder=False)
#        proposal_email.send_qaofficer_complete_email_notification(proposal, recipients, request, reminder=False)
#        proposal_email.send_referral_email_notification(referral,recipients,request,reminder=False)
#        proposal_email.send_referral_complete_email_notification(referral,request)
#        proposal_email.send_amendment_email_notification(amendment_request, request, proposal)
#        proposal_email.send_submit_email_notification(request, proposal)
#        proposal_email.send_external_submit_email_notification(request, proposal)
#        proposal_email.send_approver_decline_email_notification(reason, request, proposal)
#        proposal_email.send_approver_approve_email_notification(request, proposal)
#        proposal_email.send_proposal_decline_email_notification(proposal,request,proposal_decline)
#        proposal_email.send_proposal_approver_sendback_email_notification(request, proposal)
#        proposal_email.send_proposal_approval_email_notification(proposal,request)
#
#        approval_email.send_approval_expire_email_notification(approval)
#        approval_email.send_approval_cancel_email_notification(approval)
#        approval_email.send_approval_suspend_email_notification(approval, request)
#        approval_email.send_approval_surrender_email_notification(approval, request)
#        approval_email.send_approval_renewal_email_notification(approval)
#        approval_email.send_approval_reinstate_email_notification(approval, request)
#
#        compliance_email.send_amendment_email_notification(amendment_request, request, compliance, is_test=True)
#        compliance_email.send_reminder_email_notification(compliance, is_test=True)
#        compliance_email.send_internal_reminder_email_notification(compliance, is_test=True)
#        compliance_email.send_due_email_notification(compliance, is_test=True)
#        compliance_email.send_internal_due_email_notification(compliance, is_test=True)
#        compliance_email.send_compliance_accept_email_notification(compliance,request, is_test=True)
#        compliance_email.send_external_submit_email_notification(request, compliance, is_test=True)
#        compliance_email.send_submit_email_notification(request, compliance, is_test=True)
#
#
#        booking_email.send_application_fee_invoice_tclass_email_notification(request, proposal, api, recipients, is_test=True)
#        booking_email.send_application_fee_confirmation_tclass_email_notification(request, application_fee, api, recipients, is_test=True)
#        booking_email.send_invoice_tclass_email_notification(request.user, booking, bi, recipients, is_test=True)
#        booking_email.send_confirmation_tclass_email_notification(request.user, booking, bi, recipients, is_test=True)

