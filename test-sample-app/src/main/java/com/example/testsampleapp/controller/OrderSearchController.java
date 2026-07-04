package com.example.testsampleapp.controller;

import com.example.testsampleapp.model.Order;
import com.example.testsampleapp.model.OrderCalculationResult;
import com.example.testsampleapp.model.OrderSearchCriteria;
import com.example.testsampleapp.service.OrderCalculationService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;

import java.util.List;

@Controller
public class OrderSearchController {

    @Autowired
    private OrderCalculationService orderCalculationService;

    @GetMapping("/")
    public String index() {
        return "redirect:/order/search";
    }

    @GetMapping("/order/search")
    public String search(@ModelAttribute OrderSearchCriteria criteria, Model model) {
        List<Order> orders = orderCalculationService.searchOrders(criteria);
        model.addAttribute("criteria", criteria);
        model.addAttribute("orders", orders);
        return "order/search";
    }

    @GetMapping("/order/detail/{id}")
    public String detail(@PathVariable Integer id, Model model) {
        OrderCalculationResult result = orderCalculationService.calculateOrderAmount(id);
        model.addAttribute("result", result);
        return "order/detail";
    }
}
