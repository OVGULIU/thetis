# coding=utf-8
from collections import OrderedDict

team = OrderedDict([
    ("Tuomas Kärnä", "https://www.tuomaskarna.com"),
    ("David Ham", "http://www.imperial.ac.uk/people/david.ham"),
    ("Lawrence Mitchell",
     "http://www.imperial.ac.uk/people/lawrence.mitchell"),
    ("Stephan Kramer", "http://www.imperial.ac.uk/people/s.kramer"),
    ("Matthew Piggott", "http://www.imperial.ac.uk/people/m.d.piggott"),
    ("Athanasios Angeloudis","http://www.imperial.ac.uk/people/a.angeloudis06")
])

cols = 4
colwidth = "23%"

coldashes = max(map(len, team.keys())) + 5


def separator(n):
    out.write(("-" * coldashes).join("+" * (n + 1)) + "\n")


def blank(n):
    out.write((" " * coldashes).join("|" * (n + 1)) + "\n")

out = open("teamgrid.rst", "w")

out.write("..\n  This file is generated by team.py. DO NOT EDIT DIRECTLY\n")


images = []
names = []

def imagename(name):
    puny = name.split()[0].lower().encode("punycode").decode()
    return puny[:-1] if puny[-1]=="-" else puny

# Write substitution rules for member images.
for member, url in team.items():
    out.write(".. |" + member + "| image:: /images/" +
              imagename(member) + ".*\n")
    out.write("   :width: 70%\n")
    out.write("   :target: %s\n" % url)
    out.write(".. _" + member + ": " + url + "\n")

    im = " |" + member + "|"
    images.append(im + " " * (coldashes - len(im)))
    nm = " `" + member + "`_"
    names.append(nm + " " * (coldashes - len(nm)))

out.write("\n\n")
separator(cols)

members = zip(images, names)

try:
    while True:
        irow = "|"
        nrow = "|"
        for c in range(cols):
            image, name = next(members)
            irow += image + "|"
            nrow += name + "|"

        out.write(irow + "\n")
        blank(cols)
        out.write(nrow + "\n")

        separator(cols)

except StopIteration:

    if c > 0:
        # Finish the final row.
        for rest in range(c, cols):
            irow += " " * coldashes + "|"
            nrow += " " * coldashes + "|"

        out.write(irow + "\n")
        blank(cols)
        out.write(nrow + "\n")

        separator(cols)
