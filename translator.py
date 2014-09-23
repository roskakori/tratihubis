import re

class Translator(object):
    """
    Simple regular expression to convert Trac wiki to Github markdown.
    """
    def __init__(self, repo, ticketsToIssuesMap, trac_url=None, attachmentsPrefix=None):
        self.repo_url = r'https://github.com/{login}/{name}'.format(login=repo.owner.login, name=repo.name)
        self.trac_url = trac_url
        self.ticketsToIssuesMap = ticketsToIssuesMap
        self.subs = self.compile_subs()
        self.attachmentsPrefix = attachmentsPrefix

    def compile_subs(self):
        subs = [
            [r"\{\{\{\s*?#!python(.*?)\}\}\}", r"```python\1```"],
            [r"\{\{\{([^\n]*?)\}\}\}",  r"`\1`"],    
            [r"\{\{\{(.*?)\}\}\}",  r"```\1```"],    
            [r"====\s(.+?)\s====", r'h4. \1'],
            [r"===\s(.+?)\s===", r'h3. \1'],
            [r"==\s(.+?)\s==", r'h2. \1'],
            [r"\!(([A-Z][a-z0-9]+){2,})", r'\1'],
            [r"'''(.+)'''", r'*\1*'],
            [r"''(.+)''", r'_\1_'],
            [r"^\s\*", r'*'],
            [r"^\s\d\.", r'#'],
            [r"!(\w)", r"\1"],
            [r"(^|\n)[ ]{4,}", r"\1"],
            [r"\[([^\s\n\,\]\.\(\)]{4,}?)\s{1,}([^\n]+?)\]", r"[\2](\1)"],
            [r"(\s|^)r([0-9]{1,4})", r"\1[r\2]({trac_url}/changeset/\2/historical)".format(trac_url=self.trac_url)],
            [r"changeset:([0-9]{1,4})", r"[r\1]({trac_url}/changeset/\1/historical)".format(trac_url=self.trac_url)],
            [r"source:branches/([\w\-]*)", r"[\1](../tree/\1)"],
            [r"source:fipy/([\w/\.]*)@([0-9a-f]{5,40})", r"[\1@\2](../tree/\2/\1)"],
            [r"source:([\w/\.]*)", r"[\1](../tree/master/\1)"],
            [r"blog:(\w*)", r"[blog:\1]({trac_url}/blog/\1)".format(trac_url=self.trac_url)],
            [r"(\b)([0-9a-f]{5,40})\.", r"\1\2"],
            [r" (\w*?)::", r"#### \1"],
            [r"\[([0-9]{1,4})\/(.+?)\]", r"[\1/\2]({trac_url}/changeset/\1/historical/\2)".format(trac_url=self.trac_url)],
            [r'\[changeset:"(\S*?)\/fipy"\]', r"\1"],          
            [r'\^([0-9]{1,5})\^', r"<sup>\1</sup>"],
            [r'diff:@([0-9]{1,5}):([0-9]{1,5})', r'[diff:@\1:\2]({trac_url}/changeset?new=\2&old=\1)'.format(trac_url=self.trac_url)]
            ]

        regex = r"ticket:([0-9]{1,3})"
        sub = lambda m: r"issue #{0}".format(self.ticketsToIssuesMap[int(m.group(1))])
        subs.append([regex, sub])

        return [[re.compile(r, re.DOTALL), s] for r, s in subs]

    def no_compile_subs(self, ticketId):
        print 'ticketId',ticketId
        subs = [[r"\[\[Image\((\S*?)\,\s{0,}\S*?\)\]\]", r"![\1]({attachmentsPrefix}/{ticketId}/\1)".format(attachmentsPrefix=self.attachmentsPrefix, ticketId=ticketId)],
                [r"\[\[Image\((\S*?)\)\]\]", r"![\1]({attachmentsPrefix}/{ticketId}/\1)".format(attachmentsPrefix=self.attachmentsPrefix, ticketId=ticketId)],
                [r"attachment:(\S*?)", r"{attachmentsPrefix}/{ticketId}/\1".format(attachmentsPrefix=self.attachmentsPrefix, ticketId=ticketId)]]

        return subs
    
    def translate(self, text, ticketId=''):
        subs = self.no_compile_subs(ticketId)
        for r, s in subs:
            p = re.compile(r, re.DOTALL)
            text = p.sub(s, text)
        for p, s in self.subs:
            text = p.sub(s, text)
        
        return text

class NullTranslator(Translator):
    def translate(self, text):
        return text
