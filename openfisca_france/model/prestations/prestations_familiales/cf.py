# -*- coding: utf-8 -*-

from __future__ import division

from numpy import (round, maximum as max_, minimum as min_, logical_not as not_, logical_or as or_)

from ...base import *  # noqa analysis:ignore


class cf_enfant_a_charge(Variable):
    column = BoolCol
    entity_class = Individus
    label = u"Complément familial - Enfant considéré à charge"

    def function(self, simulation, period):
        period = period.this_month

        est_enfant_dans_famille = simulation.calculate('est_enfant_dans_famille', period)
        smic55 = simulation.calculate('smic55', period)
        age = simulation.calculate('age', period)

        pfam = simulation.legislation_at(period.start).fam

        condition_age = (age >= 0) * (age < pfam.cf.age2)
        condition_situation = est_enfant_dans_famille * not_(smic55)

        return period, condition_age * condition_situation


class cf_enfant_eligible(Variable):
    column = BoolCol
    entity_class = Individus
    label = u"Complément familial - Enfant pris en compte pour l'éligibilité"

    def function(self, simulation, period):
        period = period.this_month

        cf_enfant_a_charge = simulation.calculate('cf_enfant_a_charge', period)
        age = simulation.calculate('age', period)
        rempli_obligation_scolaire = simulation.calculate('rempli_obligation_scolaire', period)

        pfam = simulation.legislation_at(period.start).fam

        condition_enfant = ((age >= pfam.cf.age1) * (age < pfam.enfants.age_intermediaire) *
            rempli_obligation_scolaire)
        condition_jeune = (age >= pfam.enfants.age_intermediaire) * (age < pfam.cf.age2)

        return period, or_(condition_enfant, condition_jeune) * cf_enfant_a_charge


class cf_dom_enfant_eligible(Variable):
    column = BoolCol
    entity_class = Individus
    label = u"Complément familial (DOM) - Enfant pris en compte pour l'éligibilité"

    def function(self, simulation, period):
        period = period.this_month

        cf_enfant_a_charge = simulation.calculate('cf_enfant_a_charge', period)
        age = simulation.calculate('age', period)
        rempli_obligation_scolaire = simulation.calculate('rempli_obligation_scolaire', period)

        pfam = simulation.legislation_at(period.start).fam

        condition_age = (age >= pfam.cf.age1) * (age < pfam.cf.age_limite_dom)
        condition_situation = cf_enfant_a_charge * rempli_obligation_scolaire

        return period, condition_age * condition_situation


class cf_dom_enfant_trop_jeune(Variable):
    column = BoolCol
    entity_class = Individus
    label = u"Complément familial (DOM) - Enfant trop jeune pour ouvrir le droit"

    def function(self, simulation, period):
        period = period.this_month

        est_enfant_dans_famille = simulation.calculate('est_enfant_dans_famille', period)
        age = simulation.calculate('age', period)

        pfam = simulation.legislation_at(period.start).fam

        condition_age = (age >= 0) * (age < pfam.cf.age1)

        return period, condition_age * est_enfant_dans_famille


class cf_ressources_i(Variable):
    column = FloatCol
    entity_class = Individus
    label = u"Complément familial - Ressources de l'individu prises en compte"

    def function(self, simulation, period):
        period = period.this_month

        br_pf_i = simulation.calculate('br_pf_i', period)
        est_enfant_dans_famille = simulation.calculate('est_enfant_dans_famille', period)
        cf_enfant_a_charge = simulation.calculate('cf_enfant_a_charge', period)

        return period, or_(not_(est_enfant_dans_famille), cf_enfant_a_charge) * br_pf_i


class cf_plafond(Variable):
    column = FloatCol
    entity_class = Familles
    label = u"Plafond d'éligibilité au Complément Familial"

    def function(self, simulation, period):
        period = period.this_month

        pfam = simulation.legislation_at(period.start).fam

        eligibilite_base = simulation.calculate('cf_eligibilite_base', period)
        eligibilite_dom = simulation.calculate('cf_eligibilite_dom', period)
        isol = simulation.calculate('isol', period)
        biact = simulation.calculate('biact', period)
        cf_enfant_a_charge_holder = simulation.compute('cf_enfant_a_charge', period)

        # Calcul du nombre d'enfants à charge au sens du CF
        cf_nbenf = self.sum_by_entity(cf_enfant_a_charge_holder)

        # Calcul du taux à appliquer au plafond de base pour la France métropolitaine
        taux_plafond_metropole = 1 + pfam.cf.majoration_plafond_tx1 * min_(cf_nbenf, 2) + pfam.cf.majoration_plafond_tx2 * max_(cf_nbenf - 2, 0)

        # Majoration du plafond pour biactivité ou isolement (France métropolitaine)
        majoration_plafond = (isol | biact)

        # Calcul du plafond pour la France métropolitaine
        plafond_metropole = pfam.cf.plafond * taux_plafond_metropole + pfam.cf.majoration_plafond_biact_isole * majoration_plafond

        # Calcul du taux à appliquer au plafond de base pour les DOM
        taux_plafond_dom = 1 + cf_nbenf * pfam.ars.plaf_enf_supp

        # Calcul du plafond pour les DOM
        plafond_dom = pfam.ars.plaf * taux_plafond_dom

        plafond = (eligibilite_base * plafond_metropole + eligibilite_dom * plafond_dom)

        return period, plafond


class cf_majore_plafond(DatedVariable):
    column = FloatCol
    entity_class = Familles
    label = u"Plafond d'éligibilité au Complément Familial majoré"

    @dated_function(date(2014, 4, 1))
    def function(self, simulation, period):
        period = period.this_month
        plafond_base = simulation.calculate('cf_plafond', period)
        pfam = simulation.legislation_at(period.start).fam
        return period, plafond_base * pfam.cf.plafond_cf_majore


class cf_ressources(Variable):
    column = FloatCol
    entity_class = Familles
    label = u"Ressources prises en compte pour l'éligibilité au complément familial"

    def function(self, simulation, period):
        period = period.this_month
        cf_ressources_i_holder = simulation.compute('cf_ressources_i', period)
        ressources = self.sum_by_entity(cf_ressources_i_holder)
        return period, ressources


class cf_eligibilite_base(Variable):
    column = BoolCol
    entity_class = Familles
    label = u"Éligibilité au complément familial sous condition de ressources et avant cumul"

    def function(self, simulation, period):
        period = period.this_month

        residence_dom = simulation.calculate('residence_dom', period)

        cf_enfant_eligible_holder = simulation.compute('cf_enfant_eligible', period)
        cf_nbenf = self.sum_by_entity(cf_enfant_eligible_holder)

        return period, not_(residence_dom) * (cf_nbenf >= 3)

class cf_eligibilite_dom(Variable):
    column = BoolCol
    entity_class = Familles
    label = u"Éligibilité au complément familial pour les DOM sous condition de ressources et avant cumul"


    def function(self, simulation, period):
        period = period.this_month

        residence_dom = simulation.calculate('residence_dom', period)
        residence_mayotte = simulation.calculate('residence_mayotte', period)

        cf_dom_enfant_eligible_holder = simulation.compute('cf_dom_enfant_eligible', period)
        cf_nbenf = self.sum_by_entity(cf_dom_enfant_eligible_holder)

        cf_dom_enfant_trop_jeune_holder = simulation.compute('cf_dom_enfant_trop_jeune', period)
        cf_nbenf_trop_jeune = self.sum_by_entity(cf_dom_enfant_trop_jeune_holder)

        condition_composition_famille = (cf_nbenf >= 1) * (cf_nbenf_trop_jeune == 0)
        condition_residence = residence_dom * not_(residence_mayotte)

        return period, condition_composition_famille * condition_residence


class cf_non_majore_avant_cumul(Variable):
    column = FloatCol
    entity_class = Familles
    label = u"Complément familial non majoré avant cumul"

    def function(self, simulation, period):
        period = period.this_month

        eligibilite_base = simulation.calculate('cf_eligibilite_base', period)
        eligibilite_dom = simulation.calculate('cf_eligibilite_dom', period)
        ressources = simulation.calculate('cf_ressources', period)
        plafond = simulation.calculate('cf_plafond', period)

        pfam = simulation.legislation_at(period.start).fam

        eligibilite_sous_condition = or_(eligibilite_base, eligibilite_dom)

        # Montant
        montant = pfam.af.bmaf * (pfam.cf.tx * eligibilite_base + pfam.cf.tx_dom * eligibilite_dom)

        # Complément familial
        eligibilite = eligibilite_sous_condition * (ressources <= plafond)

        # Complément familial différentiel
        plafond_diff = plafond + 12 * montant
        eligibilite_diff = not_(eligibilite) * eligibilite_sous_condition * (
            ressources <= plafond_diff)
        montant_diff = (plafond_diff - ressources) / 12

        return period, max_(eligibilite * montant, eligibilite_diff * montant_diff)


class cf_majore_avant_cumul(DatedVariable):
    column = FloatCol
    entity_class = Familles
    label = u"Complément familial majoré avant cumul"

    @dated_function(date(2014, 4, 1))
    def function(self, simulation, period):
        period = period.this_month

        eligibilite_base = simulation.calculate('cf_eligibilite_base', period)
        eligibilite_dom = simulation.calculate('cf_eligibilite_dom', period)
        ressources = simulation.calculate('cf_ressources', period)
        plafond_majore = simulation.calculate('cf_majore_plafond', period)

        pfam = simulation.legislation_at(period.start).fam

        eligibilite_sous_condition = or_(eligibilite_base, eligibilite_dom)

        # Montant
        montant = pfam.af.bmaf * (pfam.cf.tx_majore * eligibilite_base + pfam.cf.tx_majore_dom * eligibilite_dom)

        eligibilite = eligibilite_sous_condition * (ressources <= plafond_majore)

        return period, eligibilite * montant


class cf_montant(Variable):
    column = FloatCol(default = 0)
    entity_class = Familles
    label = u"Montant du complément familial, avant prise en compte d'éventuels cumuls"

    def function(self, simulation, period):
        period = period.this_month

        cf_non_majore_avant_cumul = simulation.calculate('cf_non_majore_avant_cumul', period)
        cf_majore_avant_cumul = simulation.calculate('cf_majore_avant_cumul', period)

        return period, max_(cf_non_majore_avant_cumul, cf_majore_avant_cumul)


class cf(Variable):
    calculate_output = calculate_output_add
    column = FloatCol(default = 0)
    entity_class = Familles
    label = u"Complément familial"
    url = "http://vosdroits.service-public.fr/particuliers/F13214.xhtml"

    def function(self, simulation, period):
        '''
        L'allocation de base de la paje n'est pas cumulable avec le complément familial
        '''
        period = period.this_month
        paje_base = simulation.calculate('paje_base', period)
        apje_temp = simulation.calculate('apje_temp', period)
        ape_temp = simulation.calculate('ape_temp', period)
        cf_montant = simulation.calculate('cf_montant', period)
        residence_mayotte = simulation.calculate('residence_mayotte', period)

        cf_brut = not_(paje_base) * (apje_temp <= cf_montant) * (ape_temp <= cf_montant) * cf_montant
        return period, not_(residence_mayotte) * round(cf_brut, 2)
