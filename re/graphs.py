"""Entry 4 (the DSP graph library) read-only: Blob 0's composite table and member records, as worked out in
hx-effects-nam-lite. A composite is a graph made of members; a member is a primitive (a DSP routine) or another
composite, or a placeholder that something is bound into at run time. Member record: 20 words; word 6 the
primitive/composite id, words 13/14/15 its DM / PM / SDRAM memory, words 16..19 further limits."""
import struct

from fw import entry, pa


class Graphs:
    def __init__(self, app):
        self.e4 = entry(app.img, 4)
        self.w = struct.unpack('<%dI' % (len(self.e4) // 4), self.e4)
        self.d = self.w[3]
        self.b0 = self.blob(0)
        self.ct = self.b0[0x10]
        self.info = pa.parse_entry3_full(entry(app.img, 3))
        self.strings = self.info['strings']

    def blob(self, k):
        w, d = self.w, self.d
        return list(w[w[d + 2 * k + 1]: w[d + 2 * k + 1] + w[d + 2 * k]])

    def hdr(self, cid):
        o = self.ct + 7 * (cid - 0x600000)
        return self.b0[o:o + 7]

    def members(self, cid):
        h = self.hdr(cid)
        return [self.b0[h[3] + 20 * i: h[3] + 20 * i + 20] for i in range(h[2])]

    def root(self, model_name):
        m = pa.find_model(self.info, model_name)
        b = self.blob(m['blob_index'])
        return b[b[2] + 1]

    def need(self, cid):
        ms = self.members(cid)
        return sum(r[13] for r in ms), sum(r[14] for r in ms), sum(r[15] for r in ms), len(ms)
