# Copyright (C) 2006-2011, University of Maryland
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/ or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Author: Nikunj Patel

"""
This module implements the Summary View panel.
"""

#==============================================================================

from __future__ import division
import wx

import  wx.lib.scrolledpanel as scrolled

from .util import nice, publish, subscribe


class SummaryView(scrolled.ScrolledPanel):
    """
    Model view showing summary of fit (only fittable parameters).
    """

    def __init__(self, parent):
        scrolled.ScrolledPanel.__init__(self, parent, wx.ID_ANY)
        self.parent = parent

        self.display_list = []

        self.sizer = wx.GridBagSizer(hgap=0, vgap=3)
        self.SetSizer(self.sizer)
        self.sizer.Fit(self)

        self.SetAutoLayout(True)
        self.SetupScrolling()

        subscribe(self.OnModelChange, "model.change")
        subscribe(self.OnModelUpdate, "model.update")

        # Event for showing notebook tab when it is clicked.
        self.Bind(wx.EVT_SHOW, self.OnShow)

        # Keep track of whether the view needs to be redrawn.
        self._reset_model = False
        self._reset_parameters = False

    # ============= Signal bindings =========================

    def OnShow(self, event):
        if self._reset_model:
            self.update_model()
        elif self._reset_parameters:
            self.update_parameters()

    def OnModelChange(self, model):
        if self.model == model:
            self.update_model()

    def OnModelUpdate(self, model):
        if self.model == model:
            self.update_parameters()

    # ============ Operations on the model  ===============

    def set_model(self, model):
        self.model = model
        self.update_model()

    def update_model(self):
        # TODO: Need to figure how to hide/show notebook tab.
        #if not self.IsShown():
        #    print "parameter tab is hidden"
        #    self._reset_model = True
        #    return
        self._reset_model = False
        self._reset_parameters = False

        self.sizer.Clear(deleteWindows=True)
        self.display_list = []

        self.layer_label = wx.StaticText(self, wx.ID_ANY, 'Fit Parameter',
                                         size=(160,-1))
        self.slider_label = wx.StaticText(self, wx.ID_ANY, '',
                                         size=(100,-1))
        self.value_label = wx.StaticText(self, wx.ID_ANY, 'Value',
                                         size=(100,-1))
        self.low_label = wx.StaticText(self, wx.ID_ANY, 'Minimum',
                                         size=(100,-1))
        self.high_label = wx.StaticText(self, wx.ID_ANY, 'Maximum',
                                         size=(100,-1))

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(self.layer_label, 0, wx.LEFT, 1)
        hbox.Add(self.slider_label, 0, wx.LEFT, 1)
        hbox.Add(self.value_label, 0, wx.LEFT, 21)
        hbox.Add(self.low_label, 0, wx.LEFT, 1)
        hbox.Add(self.high_label, 0, wx.LEFT, 1)

        # Note that row at pos=(0,0) is not used to add a blank row.
        self.sizer.Add(hbox, pos=(1,0))

        line = wx.StaticLine(self, wx.ID_ANY)
        self.sizer.Add(line, pos=(2,0), flag=wx.EXPAND|wx.RIGHT, border=5)

        for p in sorted(self.model.parameters,
                        cmp=lambda x,y: cmp(x.name,y.name)):
            self.display_list.append(ParameterSummary(self, p, self.model))

        for index, item in enumerate(self.display_list):
            self.sizer.Add(item, pos=(index+3,0))

        self.Layout()

    def update_parameters(self):
        if not self.IsShown():
            self._reset_parameters = True
            return
        self._reset_parameters = False

        for p in self.display_list:
            p.update_slider()


class ParameterSummary(wx.Panel):
    """Build one parameter line for display."""
    def __init__(self, parent, parameter, model):
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY)

        self.parameter = parameter
        self.model = model

        self.low, self.high = (v for v in self.parameter.bounds.limits)

        text_hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.layer_name = wx.StaticText(self, wx.ID_ANY,
                                        str(self.parameter.name),
                                        size=(160,-1), style=wx.TE_LEFT)
        self.slider = wx.Slider(self, wx.ID_ANY,
                                value=0, minValue=0, maxValue=100,
                                size=(100,16), style=wx.SL_HORIZONTAL)
        self.value = wx.StaticText(self, wx.ID_ANY, str(self.parameter.value),
                                   size=(100,-1), style=wx.TE_LEFT)
        self.min_range = wx.StaticText(self, wx.ID_ANY, str(self.low),
                                       size=(100,-1), style=wx.TE_LEFT)
        self.max_range = wx.StaticText(self, wx.ID_ANY, str(self.high),
                                       size=(100,-1), style=wx.TE_LEFT)

        # Add text strings and slider to sizer.
        text_hbox.Add(self.layer_name, 0, wx.LEFT, 1)
        text_hbox.Add(self.slider, 0, wx.LEFT, 1)
        text_hbox.Add(self.value, 0, wx.LEFT, 21)
        text_hbox.Add(self.min_range, 0, wx.LEFT, 1)
        text_hbox.Add(self.max_range, 0, wx.LEFT, 1)

        self.SetSizer(text_hbox)

        self.slider.Bind(wx.EVT_SCROLL, self.OnScroll)
        self.update_slider()

    def update_slider(self):
        slider_pos = int(self.parameter.bounds.get01(self.parameter.value)*100)
        # Add line below if get01 doesn't protect against values out of range.
        #slider_pos = min(max(slider_pos,0),100)
        self.slider.SetValue(slider_pos)
        self.value.SetLabel(str(nice(self.parameter.value)))

        # Update new min and max range of values if changed.
        newlow, newhigh = (v for v in self.parameter.bounds.limits)
        if newlow != self.low:
            self.min_range.SetLabel(str(newlow))

        #if newhigh != self.high:
        self.max_range.SetLabel(str(newhigh))

    def OnScroll(self, event):
        value = self.slider.GetValue()
        new_value  = self.parameter.bounds.put01(value/100)
        self.parameter.value = new_value
        self.value.SetLabel(str(nice(new_value)))
        self.delayed_signal()

    # TODO: this code belongs in a common location! it is copied from profile.py
    def delayed_signal(self):
        try:
            self._delayed_signal.Restart(50)
        except:
            self._delayed_signal = wx.FutureCall(50, self.signal_update)

    def signal_update(self):
        self.model.model_update()  # force recalc when value changes
        publish("model.update", model=self.model)
