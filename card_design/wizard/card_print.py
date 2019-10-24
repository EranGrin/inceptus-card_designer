# -*- coding: utf-8 -*-
# Part of Inceptus ERP Solutions Pvt.ltd.
# See LICENSE file for copyright and licensing details.
from odoo import models, fields, api
import base64
import zipfile
from base64 import b64encode
import os
from os.path import basename
import datetime


class CardPrintWizard(models.TransientModel):
    _name = 'card.print.wizard'

    # @api.model
    # def _get_model(self):
    #     model = self._context.get('active_model')
    #     model_id = self.env['ir.model'].search([('model', '=', model)], limit=1)
    #     return model_id

    # @api.model
    # def get_template(self):
    #     card_template = self.env['card.template'].search(
    #         [('card_model', '=', self._context.get('active_model'))],
    #         limit=1
    #     )
    #     return card_template

    @api.model
    def default_get(self, fields):
        res = super(CardPrintWizard, self).default_get(fields)
        context = dict(self.env.context) or {}
        if context.get('active_model', False):
            model_ids = self.env['ir.model'].search([
                ('model', '=', context.get('active_model'))
            ], limit=1)
            if model_ids:
                res.update({
                    'model': model_ids and model_ids[0].id or False,
                })
        return res

    template_id = fields.Many2one(
        'card.template', 'Card Template', required=1, ondelete='cascade',
    )
    model = fields.Many2one('ir.model')
    position = fields.Selection([
        ('f', 'Front'), ('b', 'Back'), ('both', 'Both')
    ], "Position", default='f')
    file_config = fields.Selection([
        ('f', 'Only first front + all back'), ('b', ' Only first back + all front'), ('both', 'All files')
    ], "Type", default='both')
    body = fields.Html("Card Body")

    @api.onchange('template_id')
    def _preview_body(self):
        if self.template_id:
            model = self._context.get('active_model')
            res_ids = self._context.get('active_ids')
            if len(res_ids) >= 1:
                res_ids = [res_ids[0]]
            if self.position == 'b' and res_ids and self.template_id.back_side:
                template = self.env['card.template'].render_template(
                    self.template_id.back_body_html, model, res_ids
                )
                self.body = template.get(res_ids[0])
            else:
                body = self.template_id.body_html
                body = body.replace(
                    'background: url(/web/static/src/img/placeholder.png) no-repeat center;', ''
                )
                template = self.env['card.template'].render_template(
                    body, model, res_ids
                )
                self.body = template.get(res_ids[0])

    @api.onchange('position')
    def _onchange_position(self):
        model = self._context.get('active_model')
        res_ids = self._context.get('active_ids')
        if len(res_ids) >= 1:
            res_ids = [res_ids[0]]
        if res_ids:
            if self.position == 'b' and self.template_id.back_side:
                template = self.env['card.template'].render_template(
                    self.template_id.back_body_html, model, res_ids
                )
            else:
                template = self.env['card.template'].render_template(
                    self.template_id.body_html, model, res_ids
                )
            self.body = template.get(res_ids[0])

    @api.multi
    def print_pdf(self):
        context = dict(self.env.context or {})
        allow_to_zip = self.env.ref('card_design.allow_to_zip').value
        if not self.template_id:
            return True
        attachment_tuple = []
        attachment_list = []
        for cid in context.get('active_ids'):
            context.update({
                'remianing_ids': [cid]
            })
            if self.position in ['f', 'both']:
                attachment_id = self.template_id.with_context(context).pdf_generate(self.template_id.body_html, '_front_side')
                attachment_list.append(attachment_id.id)
                attachment_tuple.append(('f', attachment_id.id))
            if self.position in ['b', 'both'] and self.template_id.back_side:
                attachment_id = self.template_id.with_context(context).pdf_generate(self.template_id.back_body_html, '_back_side')
                attachment_tuple.append(('b', attachment_id.id))
                attachment_list.append(attachment_id.id)
        if self.position in ['both']:
            if self.file_config != 'both':
                front_side_list = filter(lambda x: x[0] == 'f', attachment_tuple)
                back_side_list = filter(lambda x: x[0] == 'b', attachment_tuple)
                updated_attach_list = []
                if self.file_config == 'f':
                    for position, attachment in attachment_tuple:
                        if position == 'f':
                            updated_attach_list.append(attachment)
                            for ps, attch in back_side_list:
                                updated_attach_list.append(attch)
                            break
                if self.file_config == 'b':
                    for position, attachment in attachment_tuple:
                        if position == 'b':
                            updated_attach_list.append(attachment)
                            for ps, attch in front_side_list:
                                updated_attach_list.append(attch)
                            break
                attachment_list = updated_attach_list
        actions = []
        if allow_to_zip:
            maximum_file_downalod = int(allow_to_zip)
            if maximum_file_downalod <= len(attachment_list):
                current_path = os.path.join(os.path.dirname(
                    os.path.abspath(__file__))
                ).replace('/wizard', '/static/src/export_files/')
                current_obj_name = self.template_id.name.replace(' ', '_').replace('.', '_').lower() + '_'
                zip_file_name = current_obj_name + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + '.zip'
                current_path = current_path + 'zip_files/'
                if not os.path.exists(current_path):
                    os.makedirs(current_path)
                zip_file = current_path + zip_file_name
                attachment_zipfile = zipfile.ZipFile(zip_file, 'w')
                for attachment in attachment_list:
                    attachment = self.env['ir.attachment'].browse(attachment)
                    temp_file_name = current_path.split('/card_design')[0] + attachment.card_temp_path
                    attachment_zipfile.write(temp_file_name, basename(temp_file_name))
                attachment_zipfile.close()
                base64_datas = open(current_path + zip_file_name, 'rb').read().encode('base64')
                attachment = self.env['ir.attachment'].create({
                    'name': zip_file_name,
                    'type': 'binary',
                    'mimetype': 'application/zip',
                    'datas': base64_datas,
                    'res_model': 'card.template',
                    'res_id': self.template_id.id,
                    'datas_fname': zip_file_name,
                    'card_temp_path': current_path.split('/card_design')[1] + zip_file_name,
                    'public': True
                })
                attachment_list = []
                attachment_list.append(attachment.id)
        for attachment in attachment_list:
            actions.append({
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % (attachment)
            })
        return {
            'type': 'ir.actions.multi.print',
            'actions': actions,
        }

    @api.multi
    def print_png(self):
        context = dict(self.env.context or {})
        allow_to_zip = self.env.ref('card_design.allow_to_zip').value
        if not self.template_id:
            return True
        attachment_tuple = []
        attachment_list = []
        for cid in context.get('active_ids'):
            context.update({
                'remianing_ids': [cid]
            })
            if self.position in ['f', 'both']:
                attachment_id = self.template_id.with_context(context).png_generate(self.template_id.body_html, '_front_side')
                attachment_list.append(attachment_id.id)
                attachment_tuple.append(('f', attachment_id.id))
            if self.position in ['b', 'both'] and self.template_id.back_side:
                attachment_id = self.template_id.with_context(context).png_generate(self.template_id.back_body_html, '_back_side')
                attachment_list.append(attachment_id.id)
                attachment_tuple.append(('b', attachment_id.id))
        if self.position in ['both']:
            if self.file_config != 'both':
                front_side_list = filter(lambda x: x[0] == 'f', attachment_tuple)
                back_side_list = filter(lambda x: x[0] == 'b', attachment_tuple)
                updated_attach_list = []
                if self.file_config == 'f':
                    for position, attachment in attachment_tuple:
                        if position == 'f':
                            updated_attach_list.append(attachment)
                            for ps, attch in back_side_list:
                                updated_attach_list.append(attch)
                            break
                if self.file_config == 'b':
                    for position, attachment in attachment_tuple:
                        if position == 'b':
                            updated_attach_list.append(attachment)
                            for ps, attch in front_side_list:
                                updated_attach_list.append(attch)
                            break
                attachment_list = updated_attach_list
        actions = []
        if allow_to_zip:
            maximum_file_downalod = int(allow_to_zip)
            if maximum_file_downalod <= len(attachment_list):
                current_path = os.path.join(os.path.dirname(
                    os.path.abspath(__file__))
                ).replace('/wizard', '/static/src/export_files/')
                current_obj_name = self.template_id.name.replace(' ', '_').replace('.', '_').lower() + '_'
                zip_file_name = current_obj_name + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + '.zip'
                current_path = current_path + 'zip_files/'
                if not os.path.exists(current_path):
                    os.makedirs(current_path)
                zip_file = current_path + zip_file_name
                attachment_zipfile = zipfile.ZipFile(zip_file, 'w')
                for attachment in attachment_list:
                    attachment = self.env['ir.attachment'].browse(attachment)
                    temp_file_name = current_path.split('/card_design')[0] + attachment.card_temp_path
                    attachment_zipfile.write(temp_file_name, basename(temp_file_name))
                attachment_zipfile.close()
                base64_datas = open(current_path + zip_file_name, 'rb').read().encode('base64')
                attachment = self.env['ir.attachment'].create({
                    'name': zip_file_name,
                    'type': 'binary',
                    'mimetype': 'application/zip',
                    'datas': base64_datas,
                    'res_model': 'card.template',
                    'res_id': self.template_id.id,
                    'datas_fname': zip_file_name,
                    'card_temp_path': current_path.split('/card_design')[1] + zip_file_name,
                    'public': True
                })
                attachment_list = []
                attachment_list.append(attachment.id)
        for attachment in attachment_list:
            actions.append({
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % (attachment)
            })
        return {
            'type': 'ir.actions.multi.print',
            'actions': actions,
        }


class CardExportWizard(models.TransientModel):
    _name = 'card.export.wizard'

    name = fields.Char('Name', required=1)
    template_id = fields.Many2one(
        'card.template', 'Card Template', required=1, ondelete='cascade',
    )

    @api.model
    def default_get(self, fields):
        res = super(CardExportWizard, self).default_get(fields)
        context = dict(self.env.context) or {}
        if context.get('active_id', False):
            res.update({
                'template_id': context.get('active_id'),
            })
        return res

    @api.multi
    def export(self):
        file = False
        context = dict(self.env.context or {})
        if context.get('back_side', False):
            if context.get('png', False):
                file = self.template_id.print_back_side_png_export(self.name)
            else:
                file = self.template_id.print_back_side_pdf(self.name)
        elif context.get('both_side', False):
            if context.get('png', False):
                file = self.template_id.print_both_side_png_export(self.name)
            else:
                file = self.template_id.print_both_side_pdf(self.name)
        else:
            if context.get('png', False):
                file = self.template_id.print_png_export(self.name)
            else:
                file = self.template_id.print_pdf(self.name)
        return file
