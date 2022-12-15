---
layout: archive
title: "Curriculum Vitae"
permalink: /cv/
author_profile: true
redirect_from:
  - /resume
---

{% include base_path %}

---

Education
======
* M.S. in Electrical Engineering, National Taiwan University, 2021.
  * <font size="3">Advisors: Prof. Lin-shan Lee & Prof. Hung-yi Lee</font>
  * <font size="3">Speech Processing Laboratory</font>
  * <font size="3">GPA: 4.3/4.3</font>

* B.S. in Electrical Engineering, National Taiwan University, 2019.
  * <font size="3">GPA: 4.09/4.3</font>
  * <font size="3">Rank: 26-th out of 190 students.</font>

Experience
======
  <ul>{% for post in site.exps reversed %}
    {% include archive-single-exp-cv.html %}
  {% endfor %}</ul>

Publications
======
  <ul>{% for post in site.publications reversed %}
    {% include archive-single-publication-cv.html %}
  {% endfor %}</ul>

Honors
======
  <ul>{% for post in site.honors reversed %}
    {% include archive-single-honor-cv.html %}
  {% endfor %}</ul>

Technical Skills
======
* C++
* Python
* TensorFlow
* PyTorch
* LaTeX
* Machine Learning
* Deep Learning
* Speech Processing

<!-- Talks
======
  <ul>{% for post in site.talks %}
    {% include archive-single-talk-cv.html %}
  {% endfor %}</ul> -->

<!-- Teaching
======
  <ul>{% for post in site.teaching %}
    {% include archive-single-cv.html %}
  {% endfor %}</ul>
   -->
