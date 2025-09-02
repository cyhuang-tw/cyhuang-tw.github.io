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
* Ph.D. in Language and Information Technologies, Carnegie Mellon University, 2025 - Now.
  * <font size="3">Advisor: Prof. Shinji Watanabe</font>

* M.S. in Electrical Engineering, National Taiwan University, 2019 - 2021.
  * <font size="3">Advisors: Prof. Lin-shan Lee & Prof. Hung-yi Lee</font>

* B.S. in Electrical Engineering, National Taiwan University, 2015 - 2019.

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
