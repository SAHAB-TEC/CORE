from odoo import api, fields, models
from odoo.exceptions import UserError


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    phone = fields.Char(string='Phone', compute='_compute_phone', store=True)
    invitation_title = fields.Char(string='Invitation Title', default='تمت دعوتك الي ', store=True)

    def send_whatsapp_reminder(self):
        for event in self:
            if event.phone:
                message = f"{event.invitation_title} {event.name} في {event.start}"
                whatsapp_template = self.env.ref('rgb_whatsapp_custom.rgb_new_whatsapp_template_calendar_reminder')
                if whatsapp_template:
                    whatsapp_template.message_post(event.phone, message)
                print(f"Sending WhatsApp message to {event.phone}: {message}")
            else:
                print("No phone number available for this event.")



    @api.depends('partner_ids')
    def _compute_phone(self):
        for event in self:
            phone = False
            if event.partner_ids:
                phone = event.partner_ids[0].phone
            event.phone = phone


class Attendee(models.Model):
    _inherit = 'calendar.attendee'

    event_name = fields.Char(related='event_id.name', store=True)
    event_start_date = fields.Date(related='event_id.start_date', store=True)
    event_start_time = fields.Datetime(related='event_id.start', store=True)
    event_location = fields.Char(related='event_id.location', store=True)
    event_video_link = fields.Char(related='event_id.videocall_location', store=True)
    event_description = fields.Html(related='event_id.description', store=True)


    def cron_send_whatsapp_reminder(self):
        template = self.env['whatsapp.template'].search(
            [('template_name', '=', 'calendar_event_reminder'), ('status', '=', 'approved'), ('lang_code', '=', 'ar')], limit=1
        ) # or specify manually

        if not template:
            raise UserError("No WhatsApp template found for Sale Order.")

        all_attendees = self.env['calendar.attendee'].search([('event_id.start', '>=', fields.Datetime.now())])

        for attendee in all_attendees:
            composer = self.env['whatsapp.composer'].create({
                'res_model': 'calendar.attendee',
                'res_ids': str(attendee.id),  # important: must be string, not list or int
                'wa_template_id': template.id,
                'batch_mode': False,
                'phone': attendee.partner_id.phone or attendee.partner_id.mobile or '',  # Optional if template uses dynamic phone
                'free_text_1': attendee.partner_id.name,
                'free_text_2': attendee.event_id.name,
                'free_text_3': attendee.event_id.start_date,
                'free_text_4': attendee.event_id.start,
                'free_text_5': attendee.event_id.videocall_location,
            })

            composer.action_send_whatsapp_template()

    def send_whatsapp_invite(self):
        self.ensure_one()
        attendee = self
        template = self.env['whatsapp.template'].search(
            [('template_name', '=', 'calendar'), ('status', '=', 'approved'), ('lang_code', '=', 'ar')], limit=1
        )
        if not template:
            return
        composer = self.env['whatsapp.composer'].create({
            'res_model': 'calendar.attendee',
            'res_ids': str(self.id),  # important: must be string, not list or int
            'wa_template_id': template.id,
            'batch_mode': False,
            'phone': self.partner_id.phone or self.partner_id.mobile or '',  # Optional if template uses dynamic phone
            'free_text_1': attendee.partner_id.name,
            'free_text_2': attendee.event_id.name,
            'free_text_3': attendee.event_id.start_date,
            'free_text_4': attendee.event_id.start,
            'free_text_5': attendee.event_id.videocall_location,
            'free_text_6': attendee.event_id.invitation_title,
        })
        composer.action_send_whatsapp_template()

    def create(self, vals):
        res = super(Attendee, self).create(vals)
        if res.event_id and res.event_id.start:
            res.send_whatsapp_invite()
        return res