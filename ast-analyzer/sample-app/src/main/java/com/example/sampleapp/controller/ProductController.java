package com.example.sampleapp.controller;

import com.example.sampleapp.model.Product;
import com.example.sampleapp.service.ProductService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@Controller
@RequestMapping("/product")
public class ProductController {

    @Autowired
    private ProductService productService;

    @GetMapping("/list")
    public String list(@RequestParam(value = "category", required = false) String category,
                       Model model) {
        List<Product> products;
        if (category != null && !category.isEmpty()) {
            products = productService.getProductsByCategory(category);
        } else {
            products = productService.getAllProducts();
        }
        model.addAttribute("products", products);
        model.addAttribute("category", category);
        return "product/list";
    }

    @GetMapping("/detail/{id}")
    public String detail(@PathVariable Integer id, Model model) {
        Product product = productService.getProductById(id);
        model.addAttribute("product", product);
        return "product/detail";
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("product", new Product());
        return "product/edit";
    }

    @GetMapping("/edit/{id}")
    public String editForm(@PathVariable Integer id, Model model) {
        Product product = productService.getProductById(id);
        model.addAttribute("product", product);
        return "product/edit";
    }

    @PostMapping("/create")
    public String create(@ModelAttribute Product product) {
        productService.createProduct(product);
        return "redirect:/product/list";
    }

    @PostMapping("/update")
    public String update(@ModelAttribute Product product) {
        productService.updateProduct(product);
        return "redirect:/product/detail/" + product.getId();
    }

    @PostMapping("/delete/{id}")
    public String delete(@PathVariable Integer id) {
        productService.deleteProduct(id);
        return "redirect:/product/list";
    }

    @GetMapping("/api/list")
    @ResponseBody
    public ResponseEntity<List<Product>> apiList(
            @RequestParam(value = "category", required = false) String category) {
        List<Product> products;
        if (category != null && !category.isEmpty()) {
            products = productService.getProductsByCategory(category);
        } else {
            products = productService.getAllProducts();
        }
        return ResponseEntity.ok(products);
    }

    @GetMapping("/api/detail/{id}")
    @ResponseBody
    public ResponseEntity<Product> apiDetail(@PathVariable Integer id) {
        Product product = productService.getProductById(id);
        if (product == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(product);
    }
}
