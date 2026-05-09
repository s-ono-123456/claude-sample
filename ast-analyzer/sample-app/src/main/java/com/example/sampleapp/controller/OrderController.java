package com.example.sampleapp.controller;

import com.example.sampleapp.model.Order;
import com.example.sampleapp.model.User;
import com.example.sampleapp.service.OrderService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import javax.servlet.http.HttpSession;
import java.util.List;
import java.util.Map;

@Controller
@RequestMapping("/order")
public class OrderController {

    @Autowired
    private OrderService orderService;

    @GetMapping("/list")
    public String list(HttpSession session, Model model) {
        User loginUser = (User) session.getAttribute("loginUser");
        if (loginUser == null) {
            return "redirect:/user/login";
        }
        List<Order> orders = orderService.getOrdersByUserId(loginUser.getId());
        model.addAttribute("orders", orders);
        return "order/list";
    }

    @GetMapping("/detail/{id}")
    public String detail(@PathVariable Integer id, Model model) {
        Order order = orderService.getOrderById(id);
        model.addAttribute("order", order);
        return "order/detail";
    }

    @PostMapping("/place")
    @ResponseBody
    public ResponseEntity<Map<String, Object>> place(
            @RequestBody Order order,
            HttpSession session) {
        User loginUser = (User) session.getAttribute("loginUser");
        if (loginUser == null) {
            return ResponseEntity.status(401).body(Map.of("error", "ログインが必要です"));
        }
        order.setUserId(loginUser.getId());
        try {
            orderService.placeOrder(order);
            return ResponseEntity.ok(Map.of("success", true, "orderId", order.getId()));
        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @PostMapping("/cancel/{id}")
    public String cancel(@PathVariable Integer id) {
        orderService.cancelOrder(id);
        return "redirect:/order/list";
    }

    @PostMapping("/api/complete/{id}")
    @ResponseBody
    public ResponseEntity<Map<String, Object>> complete(@PathVariable Integer id) {
        orderService.completeOrder(id);
        return ResponseEntity.ok(Map.of("success", true));
    }
}
