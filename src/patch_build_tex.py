with open("/mnt/sysfs01/users/cagatay/code/neuresearch/src/build_tex.py", "r") as f:
    text = f.read()

text = text.replace(r"\usepackage{graphicx}", "\\usepackage{graphicx}\n\\usepackage[labelformat=empty]{caption}")

with open("/mnt/sysfs01/users/cagatay/code/neuresearch/src/build_tex.py", "w") as f:
    f.write(text)
